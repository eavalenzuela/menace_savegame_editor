#!/usr/bin/env python3
"""MENACE savegame parser and editor.

Supports reading, displaying, and modifying MENACE save files.
Key feature: item cloning via UUID duplication.
"""

import struct
import uuid
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ── Binary helpers ───────────────────────────────────────────────────────────

def read_u8(data: bytes, pos: int) -> tuple[int, int]:
    return data[pos], pos + 1

def read_u16(data: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from('<H', data, pos)[0], pos + 2

def read_u32(data: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from('<I', data, pos)[0], pos + 4

def read_f32(data: bytes, pos: int) -> tuple[float, int]:
    return struct.unpack_from('<f', data, pos)[0], pos + 4

def read_f64(data: bytes, pos: int) -> tuple[float, int]:
    return struct.unpack_from('<d', data, pos)[0], pos + 8

def read_string(data: bytes, pos: int) -> tuple[str, int]:
    slen = data[pos]
    s = data[pos + 1:pos + 1 + slen].decode('utf-8', errors='replace')
    return s, pos + 1 + slen

def write_u8(val: int) -> bytes:
    return struct.pack('B', val)

def write_u16(val: int) -> bytes:
    return struct.pack('<H', val)

def write_u32(val: int) -> bytes:
    return struct.pack('<I', val)

def write_f32(val: float) -> bytes:
    return struct.pack('<f', val)

def write_f64(val: float) -> bytes:
    return struct.pack('<d', val)

def write_string(s: str) -> bytes:
    encoded = s.encode('utf-8')
    if len(encoded) > 255:
        raise ValueError(f"String too long ({len(encoded)} bytes): {s[:50]}...")
    return bytes([len(encoded)]) + encoded


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class CatalogItem:
    """An item type in the primary catalog with zero or more owned instances."""
    item_type: str
    uuids: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.uuids)

    def serialize(self) -> bytes:
        out = b'\x01' + write_string(self.item_type) + write_u32(self.count)
        for u in self.uuids:
            out += write_string(u)
        return out


@dataclass
class QualityItem:
    """An item in the quality-tagged section (Base/Regular/Tagged/SpecialOffer)."""
    item_type: str
    quality_value: int  # typically 0x7FFFFFFF
    quality: str        # "Base", "Regular", "Tagged", "SpecialOffer"
    instances: list[tuple[str, str]] = field(default_factory=list)  # (item_type, uuid)

    @property
    def count(self) -> int:
        return len(self.instances)

    def serialize(self) -> bytes:
        out = b'\x01\x01'
        out += write_string(self.item_type)
        out += write_u32(self.quality_value)
        out += write_string(self.quality)
        out += write_u32(self.count)
        for itype, iuuid in self.instances:
            out += b'\x01' + write_string(itype) + write_string(iuuid)
        return out


@dataclass
class Vehicle:
    """A player vehicle entry."""
    vehicle_type: str
    instance_uuid: str
    health1: float
    health2: float
    unknown: int

    def serialize(self) -> bytes:
        out = b'\x01'
        out += write_string(self.vehicle_type)
        out += write_string(self.instance_uuid)
        out += write_f32(self.health1)
        out += write_f32(self.health2)
        out += write_u32(self.unknown)
        return out


@dataclass
class EquipmentSlot:
    """A single equipment slot for a squad leader."""
    slot_id: int
    uuids: list[str] = field(default_factory=list)

    def serialize(self) -> bytes:
        out = write_u32(self.slot_id) + write_u32(len(self.uuids))
        for u in self.uuids:
            out += write_string(u)
        return out


@dataclass
class SquadLeader:
    """A squad leader or pilot entry."""
    class_type: str        # "Infantry" or "Vehicle"
    leader_id: str         # e.g. "squad_leader.darby", "pilot.rewa"
    stats: list[float] = field(default_factory=list)   # 7 f32 values
    perks: list[str] = field(default_factory=list)
    equipment: list[EquipmentSlot] = field(default_factory=list)
    mid_blob: bytes = b''  # mission history, battle stats (unparsed)
    status: str = 'Alive'
    known_leaders: list[int] = field(default_factory=list)  # u32 IDs

    @property
    def display_name(self) -> str:
        """Human-readable name from leader_id."""
        # "squad_leader.darby" -> "Darby", "pilot.rewa" -> "Rewa"
        name = self.leader_id.split('.')[-1]
        return name.replace('_', ' ').title()

    def serialize(self) -> bytes:
        out = write_string(self.class_type)
        out += b'\x01'
        out += write_string(self.leader_id)
        out += write_u32(len(self.stats))
        for s in self.stats:
            out += write_f32(s)
        out += write_u32(len(self.perks))
        for p in self.perks:
            out += b'\x01' + write_string(p)
        out += write_u32(len(self.equipment))
        for slot in self.equipment:
            out += slot.serialize()
        out += self.mid_blob
        out += write_string(self.status)
        out += write_u32(len(self.known_leaders))
        for kl in self.known_leaders:
            out += write_u32(kl)
        return out


@dataclass
class MenaceSave:
    """Parsed MENACE save file."""
    # Raw section blobs (for sections we don't fully parse)
    raw_data: bytes

    # Section boundaries (byte offsets in raw_data)
    header_end: int = 0
    global_stats_end: int = 0
    catalog_start: int = 0       # where catalog count u16 is
    catalog_items_start: int = 0 # where first 0x01 marker is
    catalog_end: int = 0
    known_items_start: int = 0   # "known items" list count
    known_items_end: int = 0
    quality_items_start: int = 0 # quality-tagged section count
    quality_items_end: int = 0

    # Parsed data
    catalog: list[CatalogItem] = field(default_factory=list)
    known_items: list[str] = field(default_factory=list)
    quality_items: list[QualityItem] = field(default_factory=list)
    squad_leaders: list[SquadLeader] = field(default_factory=list)

    # Pre-catalog blob (everything before the catalog count)
    pre_catalog: bytes = b''
    # Post-quality blob (everything after quality section to end of file)
    post_quality: bytes = b''
    # Blob between catalog and known items
    between_catalog_known: bytes = b''
    # Blobs around squad leaders within post_quality
    pre_squad_leaders: bytes = b''   # post_quality data before squad leader count
    post_squad_leaders: bytes = b''  # post_quality data after last squad leader


def increment_uuid(u: str) -> str:
    """Generate a new UUID by incrementing the last byte of the given UUID,
    preserving v4 format validity."""
    parsed = uuid.UUID(u)
    new_int = (parsed.int + 1) & ((1 << 128) - 1)
    # Force version 4 (bits 48-51) and variant 1 (bits 64-65) via int manipulation
    new_int = (new_int & ~(0xF << 76)) | (0x4 << 76)   # version = 4
    new_int = (new_int & ~(0xC0 << 56)) | (0x80 << 56)  # variant = 10
    return str(uuid.UUID(int=new_int))


def parse_save(filepath: str | Path) -> MenaceSave:
    """Parse a MENACE save file."""
    with open(filepath, 'rb') as f:
        data = f.read()

    save = MenaceSave(raw_data=data)

    # ── Find the catalog ─────────────────────────────────────────────────
    # The catalog is preceded by a u16 count (319 in main.save) at an offset
    # that depends on header string lengths. We find it by looking for the
    # first 0x01 marker followed by a valid "accessory." or similar string.

    # Strategy: scan for the pattern 0x01 + len + "accessory.ammo_" which is
    # reliably the first catalog entry.
    first_item_marker = data.find(b'\x01\x1daccessory.ammo_armor_piercing')
    if first_item_marker < 0:
        # Try a more general approach: find first 0x01 followed by "accessory."
        first_item_marker = data.find(b'\x01', data.find(b'accessory.') - 2)

    # The catalog count is a u16 2 bytes before the first marker,
    # preceded by 0x00 0x00
    save.catalog_items_start = first_item_marker
    save.catalog_start = first_item_marker - 4  # u16 count + 2 bytes padding

    # Actually, from our analysis: the count is at offset - 4 as u16 at catalog_start
    # Let's find it by reading backwards
    # At 0x06C4: 3f 01 00 00 = u16(319) + u16(0)
    # So catalog_start = first_item_marker - 4
    catalog_count = struct.unpack_from('<H', data, save.catalog_start)[0]

    save.pre_catalog = data[:save.catalog_start]

    # ── Parse catalog items ──────────────────────────────────────────────
    pos = save.catalog_items_start
    for i in range(catalog_count):
        marker, pos = read_u8(data, pos)
        assert marker == 0x01, f"Expected 0x01 marker at 0x{pos-1:04x}, got 0x{marker:02x}"
        item_type, pos = read_string(data, pos)
        inst_count, pos = read_u32(data, pos)
        uuids = []
        for _ in range(inst_count):
            u, pos = read_string(data, pos)
            uuids.append(u)
        save.catalog.append(CatalogItem(item_type=item_type, uuids=uuids))

    save.catalog_end = pos

    # ── Parse known items list ───────────────────────────────────────────
    known_count, pos = read_u32(data, pos)
    save.known_items_start = save.catalog_end
    for i in range(known_count):
        marker, pos = read_u8(data, pos)
        item_name, pos = read_string(data, pos)
        save.known_items.append(item_name)
    save.known_items_end = pos

    # ── Parse quality-tagged items ───────────────────────────────────────
    quality_count, pos = read_u32(data, pos)
    save.quality_items_start = save.known_items_end

    for i in range(quality_count):
        outer_marker, pos = read_u8(data, pos)
        flag, pos = read_u8(data, pos)
        item_type, pos = read_string(data, pos)
        quality_value, pos = read_u32(data, pos)
        quality, pos = read_string(data, pos)
        inst_count, pos = read_u32(data, pos)

        instances = []
        for _ in range(inst_count):
            inst_marker, pos = read_u8(data, pos)
            itype, pos = read_string(data, pos)
            iuuid, pos = read_string(data, pos)
            instances.append((itype, iuuid))

        save.quality_items.append(QualityItem(
            item_type=item_type,
            quality_value=quality_value,
            quality=quality,
            instances=instances,
        ))

    save.quality_items_end = pos
    save.post_quality = data[pos:]

    # ── Parse squad leaders from post_quality ─────────────────────────────
    save.squad_leaders, save.pre_squad_leaders, save.post_squad_leaders = \
        _parse_squad_leaders(save.post_quality)

    return save


def _find_squad_leader_start(data: bytes) -> int | None:
    """Find the offset of the squad leader count u32 within a data blob.

    Looks for the pattern: u32(count) + string("Infantry"|"Vehicle") + 0x01 +
    string("squad_leader.*"|"pilot.*")
    """
    import re
    for m in re.finditer(b'(\x08Infantry|\x07Vehicle)\x01', data):
        pos = m.end()
        if pos >= len(data):
            continue
        slen = data[pos]
        if pos + 1 + slen > len(data):
            continue
        name = data[pos + 1:pos + 1 + slen].decode('utf-8', errors='replace')
        if 'squad_leader.' in name or 'pilot.' in name:
            # Count u32 is 4 bytes before the class string
            count_pos = m.start() - 4
            if count_pos < 0:
                continue
            count = struct.unpack_from('<I', data, count_pos)[0]
            if 1 <= count <= 20:  # sanity check
                return count_pos
    return None


def _parse_squad_leaders(post_quality: bytes) -> tuple[list['SquadLeader'], bytes, bytes]:
    """Parse squad leaders from post_quality blob.

    Returns (squad_leaders, pre_blob, post_blob).
    """
    count_offset = _find_squad_leader_start(post_quality)
    if count_offset is None:
        return [], post_quality, b''

    pre_blob = post_quality[:count_offset]
    pos = count_offset
    sl_count = struct.unpack_from('<I', post_quality, pos)[0]
    pos += 4

    leaders = []
    for _ in range(sl_count):
        class_type, pos = read_string(post_quality, pos)
        _marker, pos = read_u8(post_quality, pos)
        leader_id, pos = read_string(post_quality, pos)

        stat_count, pos = read_u32(post_quality, pos)
        stats = []
        for _i in range(stat_count):
            val, pos = read_f32(post_quality, pos)
            stats.append(val)

        perk_count, pos = read_u32(post_quality, pos)
        perks = []
        for _i in range(perk_count):
            _m, pos = read_u8(post_quality, pos)
            perk_name, pos = read_string(post_quality, pos)
            perks.append(perk_name)

        equip_count, pos = read_u32(post_quality, pos)
        equipment = []
        for _i in range(equip_count):
            slot_id, pos = read_u32(post_quality, pos)
            uuid_count, pos = read_u32(post_quality, pos)
            slot_uuids = []
            for _j in range(uuid_count):
                uid, pos = read_string(post_quality, pos)
                slot_uuids.append(uid)
            equipment.append(EquipmentSlot(slot_id=slot_id, uuids=slot_uuids))

        equip_end = pos

        # Find status string ("Alive" or "Dead") — mid_blob is everything between
        alive_pos = post_quality.find(b'\x05Alive', pos)
        dead_pos = post_quality.find(b'\x04Dead', pos)
        candidates = [(p, 'Alive') for p in [alive_pos] if 0 < p < pos + 3000]
        candidates += [(p, 'Dead') for p in [dead_pos] if 0 < p < pos + 3000]
        candidates.sort()

        if not candidates:
            raise ValueError(f"Could not find status for {leader_id}")

        status_pos = candidates[0][0]
        mid_blob = post_quality[equip_end:status_pos]

        status, pos = read_string(post_quality, status_pos)
        known_count, pos = read_u32(post_quality, pos)
        known_leaders = []
        for _i in range(known_count):
            kl, pos = read_u32(post_quality, pos)
            known_leaders.append(kl)

        leaders.append(SquadLeader(
            class_type=class_type,
            leader_id=leader_id,
            stats=stats,
            perks=perks,
            equipment=equipment,
            mid_blob=mid_blob,
            status=status,
            known_leaders=known_leaders,
        ))

    post_blob = post_quality[pos:]
    return leaders, pre_blob, post_blob


def serialize_save(save: MenaceSave) -> bytes:
    """Serialize a MenaceSave back to binary."""
    out = bytearray(save.pre_catalog)

    # Catalog count (u16 + u16 padding)
    out += write_u16(len(save.catalog))
    out += write_u16(0)

    # Catalog items
    for item in save.catalog:
        out += item.serialize()

    # Known items
    out += write_u32(len(save.known_items))
    for name in save.known_items:
        out += b'\x01' + write_string(name)

    # Quality-tagged items
    out += write_u32(len(save.quality_items))
    for qi in save.quality_items:
        out += qi.serialize()

    # Post-quality: pre_squad_leaders + squad leaders + post_squad_leaders
    out += save.pre_squad_leaders
    if save.squad_leaders:
        out += write_u32(len(save.squad_leaders))
        for sl in save.squad_leaders:
            out += sl.serialize()
    out += save.post_squad_leaders

    return bytes(out)


def find_item(save: MenaceSave, search: str) -> list[tuple[str, int, CatalogItem]]:
    """Find catalog items matching a search string (case-insensitive)."""
    results = []
    search_lower = search.lower()
    for idx, item in enumerate(save.catalog):
        if search_lower in item.item_type.lower():
            results.append(('catalog', idx, item))
    return results


def find_quality_item(save: MenaceSave, search: str) -> list[tuple[str, int, QualityItem]]:
    """Find quality items matching a search string."""
    results = []
    search_lower = search.lower()
    for idx, item in enumerate(save.quality_items):
        if search_lower in item.item_type.lower():
            results.append(('quality', idx, item))
    return results


def clone_catalog_item(save: MenaceSave, item_idx: int, count: int = 1) -> list[str]:
    """Clone an owned catalog item by duplicating with new UUIDs.
    Returns the new UUIDs created."""
    item = save.catalog[item_idx]
    if not item.uuids:
        raise ValueError(f"Item '{item.item_type}' has no owned instances to clone from")

    source_uuid = item.uuids[-1]
    new_uuids = []
    current = source_uuid
    for _ in range(count):
        current = increment_uuid(current)
        item.uuids.append(current)
        new_uuids.append(current)

    return new_uuids


def clone_quality_item(save: MenaceSave, item_idx: int, count: int = 1) -> list[str]:
    """Clone a quality-tagged item."""
    item = save.quality_items[item_idx]
    if not item.instances:
        raise ValueError(f"Item '{item.item_type}' has no instances to clone from")

    source_type, source_uuid = item.instances[-1]
    new_uuids = []
    current = source_uuid
    for _ in range(count):
        current = increment_uuid(current)
        item.instances.append((source_type, current))
        new_uuids.append(current)

    return new_uuids


def print_inventory(save: MenaceSave):
    """Print all owned items."""
    print("═══ Owned Items (Catalog) ═══")
    for item in save.catalog:
        if item.count > 0:
            print(f"  {item.item_type} x{item.count}")
            for u in item.uuids:
                print(f"    {u}")

    print("\n═══ Quality Items ═══")
    for qi in save.quality_items:
        print(f"  [{qi.quality}] {qi.item_type} x{qi.count}")
        for itype, iuuid in qi.instances:
            print(f"    {iuuid}")


def print_summary(save: MenaceSave):
    """Print a compact summary."""
    owned_catalog = sum(1 for i in save.catalog if i.count > 0)
    total_instances = sum(i.count for i in save.catalog)
    print(f"Catalog: {len(save.catalog)} types, {owned_catalog} owned, {total_instances} instances")
    print(f"Known items: {len(save.known_items)}")
    total_quality = sum(qi.count for qi in save.quality_items)
    print(f"Quality items: {len(save.quality_items)} entries, {total_quality} instances")


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_list(args):
    save = parse_save(args[0])
    print_summary(save)
    print()
    print_inventory(save)


def cmd_search(args):
    save = parse_save(args[0])
    query = args[1]
    results = find_item(save, query)
    qresults = find_quality_item(save, query)
    if not results and not qresults:
        print(f"No items matching '{query}'")
        return
    for section, idx, item in results:
        print(f"[catalog #{idx}] {item.item_type} x{item.count}")
        for u in item.uuids:
            print(f"  {u}")
    for section, idx, item in qresults:
        print(f"[quality #{idx}] [{item.quality}] {item.item_type} x{item.count}")
        for itype, iuuid in item.instances:
            print(f"  {iuuid}")


def cmd_clone(args):
    filepath = args[0]
    query = args[1]
    count = int(args[2]) if len(args) > 2 else 1
    output = args[3] if len(args) > 3 else None

    save = parse_save(filepath)

    # Search both sections
    results = find_item(save, query)
    qresults = find_quality_item(save, query)

    all_results = [(s, i, r) for s, i, r in results if r.count > 0]
    all_results += [(s, i, r) for s, i, r in qresults if r.count > 0]

    if not all_results:
        # Check if items exist but aren't owned
        if results or qresults:
            print(f"Found items matching '{query}' but none are owned (no instances to clone from)")
        else:
            print(f"No items matching '{query}'")
        return

    if len(all_results) > 1:
        # If all matches have the same item_type, clone all of them
        types = set()
        for s, i, r in all_results:
            types.add(r.item_type if isinstance(r, CatalogItem) else r.item_type)
        if len(types) > 1:
            print(f"Multiple item types match '{query}':")
            for section, idx, item in all_results:
                if isinstance(item, CatalogItem):
                    print(f"  [{section} #{idx}] {item.item_type} x{item.count}")
                else:
                    print(f"  [{section} #{idx}] [{item.quality}] {item.item_type} x{item.count}")
            print("Refine your search to match a single item type.")
            return

    all_new_uuids = []
    for section, idx, item in all_results:
        if section == 'catalog':
            new_uuids = clone_catalog_item(save, idx, count)
            print(f"Cloned {item.item_type} x{count} (now x{item.count})")
        else:
            new_uuids = clone_quality_item(save, idx, count)
            print(f"Cloned [{item.quality}] {item.item_type} x{count} (now x{item.count})")
        all_new_uuids.extend(new_uuids)

    for u in all_new_uuids:
        print(f"  new: {u}")

    # Save
    out_path = output or filepath
    if out_path == filepath:
        backup = Path(filepath).with_suffix('.save.bak')
        print(f"Backing up to {backup}")
        with open(backup, 'wb') as f:
            f.write(save.raw_data)

    new_data = serialize_save(save)
    with open(out_path, 'wb') as f:
        f.write(new_data)
    print(f"Saved to {out_path} ({len(new_data)} bytes)")


def cmd_verify(args):
    """Parse, serialize, and compare to verify round-trip fidelity."""
    filepath = args[0]
    save = parse_save(filepath)
    new_data = serialize_save(save)

    with open(filepath, 'rb') as f:
        original = f.read()

    if new_data == original:
        print("Round-trip OK: serialized output matches original exactly.")
    else:
        print(f"MISMATCH: original={len(original)} bytes, serialized={len(new_data)} bytes")
        # Find first difference
        for i in range(min(len(original), len(new_data))):
            if original[i] != new_data[i]:
                print(f"First difference at offset 0x{i:04x}: orig=0x{original[i]:02x} new=0x{new_data[i]:02x}")
                break


USAGE = """\
Usage: menace_save.py <command> <savefile> [args...]

Commands:
  list   <file>                     Show all owned items
  search <file> <query>             Search for items by name
  clone  <file> <query> [n] [out]   Clone owned item n times (default 1)
  verify <file>                     Verify round-trip parse/serialize
"""


def main():
    if len(sys.argv) < 3:
        print(USAGE)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        'list': cmd_list,
        'search': cmd_search,
        'clone': cmd_clone,
        'verify': cmd_verify,
    }

    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        print(USAGE)
        sys.exit(1)

    commands[cmd](args)


if __name__ == '__main__':
    main()
