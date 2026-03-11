#!/usr/bin/env python3
"""MENACE savegame editor — tkinter GUI."""

import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import uuid

from menace_save import (
    MenaceSave, CatalogItem, SquadLeader,
    parse_save, serialize_save,
    increment_uuid,
)

# ── Global stats config ─────────────────────────────────────────────────────

GLOBAL_STATS_COUNT = 20

STAT_LABELS = {
    0: "Count field",
    1: "Unknown #1",
    2: "OCI Components",
    3: "Promotion Points",
    4: "Stat #4",
    5: "Stat #5",
    6: "Stat #6",
    7: "Stat #7",
    8: "Stat #8",
    9: "Stat #9",
    10: "Stat #10",
    11: "Stat #11",
    12: "Stat #12",
    13: "Stat #13",
    14: "Intelligence",
    15: "Stat #15",
    16: "Authority",
    17: "Stat #17",
    18: "Stat #18",
    19: "Stat #19",
}


def _find_stats_offset(data: bytes) -> int:
    """Find the byte offset where global stats begin.

    Stats follow the second occurrence of 'global_difficulty.normal'
    in the pre-catalog header. The offset varies with header string lengths.
    """
    needle = b'global_difficulty.normal'
    first = data.find(needle)
    if first < 0:
        raise ValueError("Could not find 'global_difficulty.normal' in header")
    second = data.find(needle, first + len(needle))
    if second < 0:
        raise ValueError("Could not find second 'global_difficulty.normal' in header")
    return second + len(needle)


def read_global_stats(pre_catalog: bytes) -> list[int]:
    """Read global stats u32 values from pre_catalog blob."""
    offset = _find_stats_offset(pre_catalog)
    stats = []
    for i in range(GLOBAL_STATS_COUNT):
        off = offset + i * 4
        if off + 4 <= len(pre_catalog):
            val = struct.unpack_from('<I', pre_catalog, off)[0]
            stats.append(val)
        else:
            stats.append(0)
    return stats


def write_global_stats(pre_catalog: bytearray, stats: list[int]) -> bytearray:
    """Write global stats back into pre_catalog blob."""
    buf = bytearray(pre_catalog)
    offset = _find_stats_offset(bytes(buf))
    for i, val in enumerate(stats):
        off = offset + i * 4
        if off + 4 <= len(buf):
            struct.pack_into('<I', buf, off, val)
    return buf


def item_category(item_type: str) -> str:
    """Extract category prefix from an item type string."""
    dot = item_type.find('.')
    if dot > 0:
        return item_type[:dot]
    return item_type


# ── Main application ────────────────────────────────────────────────────────

class MenaceEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MENACE Savegame Editor")
        self.geometry("950x620")
        self.minsize(750, 450)

        self.save: MenaceSave | None = None
        self.filepath: str | None = None
        self.stat_vars: list[tk.StringVar] = []
        self.sl_stat_vars: dict[int, list[tk.StringVar]] = {}  # squad leader idx -> stat vars
        self.sl_perk_vars: dict[int, dict[str, tk.BooleanVar]] = {}  # squad leader idx -> perk -> var

        self._build_ui()

    # ── UI construction ─────────────────────────────────────────────────

    def _build_ui(self):
        # File bar
        file_frame = ttk.Frame(self)
        file_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        ttk.Label(file_frame, text="File:").pack(side=tk.LEFT)
        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, state="readonly")
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        ttk.Button(file_frame, text="Open", command=self._open_file).pack(side=tk.LEFT, padx=2)
        self.save_btn = ttk.Button(file_frame, text="Save", command=self._save_file, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=2)
        self.saveas_btn = ttk.Button(file_frame, text="Save As", command=self._save_file_as, state=tk.DISABLED)
        self.saveas_btn.pack(side=tk.LEFT, padx=2)

        # Main paned window
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # Left: tabs
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        self.notebook = ttk.Notebook(left)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_inventory_tab()
        self._build_stats_tab()
        self._build_squad_leaders_tab()

        # Right: details
        self.detail_frame = ttk.LabelFrame(paned, text="Details")
        paned.add(self.detail_frame, weight=1)

        self.detail_placeholder = ttk.Label(self.detail_frame, text="Open a save file and\nselect an item to view details.",
                                            justify=tk.CENTER, foreground="gray")
        self.detail_placeholder.pack(expand=True)

        # Status bar
        self.status_var = tk.StringVar(value="No file loaded.")
        status = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(fill=tk.X, padx=6, pady=(0, 6))

    def _build_inventory_tab(self):
        inv_frame = ttk.Frame(self.notebook)
        self.notebook.add(inv_frame, text="Inventory")

        # Search + show all
        top = ttk.Frame(inv_frame)
        top.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(top, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_tree())
        search_entry = ttk.Entry(top, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))

        self.show_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Show all", variable=self.show_all_var,
                        command=self._refresh_tree).pack(side=tk.LEFT)

        # Treeview
        tree_frame = ttk.Frame(inv_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self.tree = ttk.Treeview(tree_frame, columns=("count",), selectmode="browse")
        self.tree.heading("#0", text="Item", anchor=tk.W)
        self.tree.heading("count", text="Owned", anchor=tk.W)
        self.tree.column("count", width=60, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _build_stats_tab(self):
        stats_outer = ttk.Frame(self.notebook)
        self.notebook.add(stats_outer, text="Global Values")

        canvas = tk.Canvas(stats_outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(stats_outer, orient=tk.VERTICAL, command=canvas.yview)
        self.stats_frame = ttk.Frame(canvas)

        self.stats_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.stats_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_squad_leaders_tab(self):
        sl_outer = ttk.Frame(self.notebook)
        self.notebook.add(sl_outer, text="Squad Leaders")

        # Left: leader list
        list_frame = ttk.Frame(sl_outer)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0), pady=4)

        ttk.Label(list_frame, text="Leaders", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, padx=4)
        self.sl_listbox = tk.Listbox(list_frame, width=22, exportselection=False)
        self.sl_listbox.pack(fill=tk.Y, expand=True, padx=4, pady=4)
        self.sl_listbox.bind("<<ListboxSelect>>", self._on_sl_select)

        # Right: details (scrollable)
        detail_outer = ttk.Frame(sl_outer)
        detail_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        canvas = tk.Canvas(detail_outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(detail_outer, orient=tk.VERTICAL, command=canvas.yview)
        self.sl_detail_frame = ttk.Frame(canvas)

        self.sl_detail_frame.bind("<Configure>",
                                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sl_detail_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ── File operations ─────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open MENACE Save",
            filetypes=[("Save files", "*.save"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.save = parse_save(path)
            self.filepath = path
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse save:\n{e}")
            return

        self.file_var.set(path)
        self.save_btn.configure(state=tk.NORMAL)
        self.saveas_btn.configure(state=tk.NORMAL)

        owned = sum(1 for i in self.save.catalog if i.count > 0)
        total = sum(i.count for i in self.save.catalog)
        self.status_var.set(f"Loaded {Path(path).name}  —  {len(self.save.catalog)} item types, "
                           f"{owned} owned, {total} instances")

        self._refresh_tree()
        self._refresh_stats()
        self._refresh_squad_leaders()
        self._clear_details()

    def _save_file(self):
        if not self.save or not self.filepath:
            return
        self._apply_stats()
        self._apply_squad_leaders()
        self._do_save(self.filepath)

    def _save_file_as(self):
        if not self.save:
            return
        path = filedialog.asksaveasfilename(
            title="Save As",
            defaultextension=".save",
            filetypes=[("Save files", "*.save"), ("All files", "*.*")],
        )
        if not path:
            return
        self._apply_stats()
        self._apply_squad_leaders()
        self._do_save(path)

    def _do_save(self, path: str):
        # Backup if overwriting the original
        if path == self.filepath:
            backup = Path(path).with_suffix('.save.bak')
            with open(path, 'rb') as f:
                backup.write_bytes(f.read())

        try:
            data = serialize_save(self.save)
            with open(path, 'wb') as f:
                f.write(data)
            self.status_var.set(f"Saved to {Path(path).name} ({len(data)} bytes)")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    # ── Inventory tree ──────────────────────────────────────────────────

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.save:
            return

        search = self.search_var.get().lower()
        show_all = self.show_all_var.get()

        # Group items by category
        categories: dict[str, list[tuple[int, CatalogItem]]] = {}
        for idx, item in enumerate(self.save.catalog):
            if not show_all and item.count == 0:
                continue
            if search and search not in item.item_type.lower():
                continue
            cat = item_category(item.item_type)
            categories.setdefault(cat, []).append((idx, item))

        for cat in sorted(categories):
            items = categories[cat]
            owned_in_cat = sum(i.count for _, i in items)
            cat_id = self.tree.insert("", tk.END, text=cat,
                                      values=(f"{owned_in_cat}",),
                                      open=bool(search))
            for idx, item in items:
                # Strip category prefix for cleaner display
                short = item.item_type[len(cat)+1:] if item.item_type.startswith(cat + ".") else item.item_type
                count_str = str(item.count) if item.count > 0 else "-"
                self.tree.insert(cat_id, tk.END, text=short,
                                 values=(count_str,),
                                 tags=(str(idx),))

    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        tags = self.tree.item(sel[0], "tags")
        if not tags:
            # Category row selected
            self._clear_details()
            return
        idx = int(tags[0])
        self._show_item_details(idx)

    # ── Details panel ───────────────────────────────────────────────────

    def _clear_details(self):
        for w in self.detail_frame.winfo_children():
            w.destroy()
        self.detail_placeholder = ttk.Label(self.detail_frame,
                                            text="Select an item to view details.",
                                            justify=tk.CENTER, foreground="gray")
        self.detail_placeholder.pack(expand=True)

    def _show_item_details(self, idx: int):
        for w in self.detail_frame.winfo_children():
            w.destroy()

        item = self.save.catalog[idx]
        pad = dict(padx=8, pady=2)

        ttk.Label(self.detail_frame, text=item.item_type,
                  font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Label(self.detail_frame, text=f"Owned: {item.count}").pack(anchor=tk.W, **pad)

        if item.uuids:
            ttk.Separator(self.detail_frame).pack(fill=tk.X, padx=8, pady=6)
            ttk.Label(self.detail_frame, text="UUIDs:").pack(anchor=tk.W, **pad)

            uuid_frame = ttk.Frame(self.detail_frame)
            uuid_frame.pack(fill=tk.BOTH, expand=True, padx=8)

            uuid_list = tk.Listbox(uuid_frame, height=min(len(item.uuids), 8),
                                   font=("TkFixedFont", 9))
            uuid_sb = ttk.Scrollbar(uuid_frame, orient=tk.VERTICAL, command=uuid_list.yview)
            uuid_list.configure(yscrollcommand=uuid_sb.set)
            for u in item.uuids:
                uuid_list.insert(tk.END, u)
            uuid_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            uuid_sb.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Separator(self.detail_frame).pack(fill=tk.X, padx=8, pady=6)

        # Action buttons
        action_frame = ttk.Frame(self.detail_frame)
        action_frame.pack(anchor=tk.W, padx=8, pady=4)

        count_var = tk.IntVar(value=max(item.count, 1))
        ttk.Label(action_frame, text="Count:").grid(row=0, column=0, padx=(0, 4))
        count_spin = ttk.Spinbox(action_frame, from_=0, to=999, width=5,
                                 textvariable=count_var)
        count_spin.grid(row=0, column=1, padx=(0, 8))

        ttk.Button(action_frame, text="Set Count",
                   command=lambda: self._set_item_count(idx, count_var.get())
                   ).grid(row=0, column=2, padx=2)

    def _set_item_count(self, idx: int, target: int):
        item = self.save.catalog[idx]
        current = item.count
        if target == current:
            return
        if target < 0:
            target = 0

        if target > current:
            # Add instances
            to_add = target - current
            if item.uuids:
                last = item.uuids[-1]
            else:
                last = str(uuid.uuid4())
                item.uuids.append(last)
                to_add -= 1
            for _ in range(to_add):
                last = increment_uuid(last)
                item.uuids.append(last)
            self.status_var.set(f"Set {item.item_type} to x{item.count}  (+{target - current})")
        else:
            # Remove from the end
            removed = current - target
            del item.uuids[target:]
            self.status_var.set(f"Set {item.item_type} to x{item.count}  (-{removed})")

        self._refresh_tree()
        self._show_item_details(idx)

    # ── Stats tab ───────────────────────────────────────────────────────

    def _refresh_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        self.stat_vars.clear()

        if not self.save:
            return

        stats = read_global_stats(self.save.pre_catalog)
        base_offset = _find_stats_offset(self.save.pre_catalog)

        ttk.Label(self.stats_frame, text="Global Stats",
                  font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, columnspan=2,
                                                           sticky=tk.W, padx=8, pady=(8, 4))

        for i, val in enumerate(stats):
            label = STAT_LABELS.get(i, f"Stat #{i}")
            offset = base_offset + i * 4
            display = f"{label}  (0x{offset:04X})"

            ttk.Label(self.stats_frame, text=display).grid(row=i+1, column=0,
                                                           sticky=tk.W, padx=(8, 4), pady=2)
            var = tk.StringVar(value=str(val))
            self.stat_vars.append(var)
            entry = ttk.Entry(self.stats_frame, textvariable=var, width=12)
            entry.grid(row=i+1, column=1, sticky=tk.W, padx=(0, 8), pady=2)

    def _apply_stats(self):
        """Write stat entry values back into pre_catalog."""
        if not self.save or not self.stat_vars:
            return
        stats = []
        for i, var in enumerate(self.stat_vars):
            try:
                stats.append(int(var.get()))
            except ValueError:
                label = STAT_LABELS.get(i, f"Stat #{i}")
                messagebox.showerror("Invalid value", f"{label} must be an integer.")
                return
        self.save.pre_catalog = bytes(write_global_stats(bytearray(self.save.pre_catalog), stats))

    # ── Squad Leaders tab ────────────────────────────────────────────────

    STAT_NAMES = ["Accuracy", "Toughness", "Leadership", "Stat 4", "Stat 5", "Experience", "Morale"]

    # Known perks per leader (union of observed perks across saves).
    # Unique perks are listed first, then alphabetical.
    KNOWN_PERKS: dict[str, list[str]] = {
        "squad_leader.darby": [
            "perk.unique_darby_high_value_targets",
            "perk.ambush", "perk.athletic", "perk.commando", "perk.covert_ops",
            "perk.impossible_shot", "perk.minimize_silhouette", "perk.scout",
            "perk.sharpshooter", "perk.take_aim",
        ],
        "squad_leader.pike": [
            "perk.stalwart_pike_unique",
            "perk.athletic", "perk.call_out_target", "perk.determined",
            "perk.fortify", "perk.inspiring_presence", "perk.new_tricks",
            "perk.scout", "perk.solid_grouping", "perk.standby",
            "perk.taking_command", "perk.this_is_my_rifle",
        ],
        "squad_leader.carda": [
            "perk.unique_carda_out_of_the_craters",
            "perk.athletic", "perk.first_aid", "perk.hit_the_deck",
            "perk.scout", "perk.share_the_load", "perk.steady_gun",
            "perk.stubborn", "perk.team_spirit",
        ],
        "squad_leader.wetteroth": [
            "perk.unique_wetteroth_big_game_hunter",
            "perk.buff", "perk.critical_hits", "perk.finisher",
            "perk.finishing_shot", "perk.if_it_bleeds",
            "perk.minimize_silhouette", "perk.scout",
        ],
        "squad_leader.greifinger": [
            "perk.unique_greifinger_guerilla",
            "perk.assassin", "perk.athletic", "perk.fortify",
            "perk.recover", "perk.scout", "perk.sharpshooter",
            "perk.tankbuster",
        ],
        "squad_leader.lim": [
            "perk.unique_aspiring_lim",
            "perk.athletic", "perk.berserk", "perk.counter_strike",
            "perk.return_of_serve", "perk.run_and_gun", "perk.scout",
            "perk.stubborn",
        ],
        "pilot.rewa": [
            "perk.unique_rewa_revel_in_slaughter",
            "perk.commando", "perk.expert_pilot_vehicle", "perk.grind_down",
            "perk.roadkill", "perk.tankbuster", "perk.unbreakable_vehicle",
            "perk.vanguard",
        ],
        "pilot.exconde": [
            "perk.unique_sentry",
            "perk.expert_pilot_vehicle", "perk.hotwire_vehicle",
            "perk.scout", "perk.sharpshooter", "perk.tankbuster",
            "perk.unbreakable_vehicle", "perk.zig_zag",
        ],
        "pilot.ivey": [
            "perk.zero_in_starting",
            "perk.barrage", "perk.demolitions_expert",
            "perk.expert_pilot_vehicle", "perk.full_send", "perk.standby",
            "perk.steady_gun", "perk.tankbuster", "perk.to_shreds_vehicle",
        ],
    }

    def _refresh_squad_leaders(self):
        self.sl_listbox.delete(0, tk.END)
        self.sl_stat_vars.clear()
        self.sl_perk_vars.clear()
        for w in self.sl_detail_frame.winfo_children():
            w.destroy()

        if not self.save:
            return

        for sl in self.save.squad_leaders:
            prefix = "SL" if "squad_leader" in sl.leader_id else "P"
            self.sl_listbox.insert(tk.END, f"[{prefix}] {sl.display_name}")

    def _on_sl_select(self, _event=None):
        sel = self.sl_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self._show_squad_leader(idx)

    def _show_squad_leader(self, idx: int):
        for w in self.sl_detail_frame.winfo_children():
            w.destroy()

        sl = self.save.squad_leaders[idx]
        row = 0

        # Header
        ttk.Label(self.sl_detail_frame, text=f"{sl.display_name}  ({sl.class_type})",
                  font=("TkDefaultFont", 11, "bold")).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(8, 2))
        row += 1

        ttk.Label(self.sl_detail_frame, text=f"Status: {sl.status}",
                  foreground="green" if sl.status == "Alive" else "red").grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(0, 6))
        row += 1

        # Stats
        ttk.Label(self.sl_detail_frame, text="Stats",
                  font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(4, 2))
        row += 1

        stat_vars = []
        for i, val in enumerate(sl.stats):
            name = self.STAT_NAMES[i] if i < len(self.STAT_NAMES) else f"Stat {i+1}"
            ttk.Label(self.sl_detail_frame, text=name).grid(
                row=row, column=0, sticky=tk.W, padx=(16, 4), pady=1)
            var = tk.StringVar(value=repr(val))
            stat_vars.append(var)
            ttk.Entry(self.sl_detail_frame, textvariable=var, width=20).grid(
                row=row, column=1, sticky=tk.W, padx=(0, 8), pady=1)
            row += 1

        self.sl_stat_vars[idx] = stat_vars

        # Perks
        ttk.Separator(self.sl_detail_frame).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, padx=8, pady=6)
        row += 1

        ttk.Label(self.sl_detail_frame, text="Perks",
                  font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(4, 2))
        row += 1

        perk_vars = {}
        active_perks = set(sl.perks)

        # Build full perk list: known perks for this leader + any unknown active perks
        known = self.KNOWN_PERKS.get(sl.leader_id, [])
        all_perks = list(known)
        for p in sl.perks:
            if p not in all_perks:
                all_perks.append(p)

        for perk in all_perks:
            display = perk.removeprefix("perk.").replace("_", " ").title()
            is_active = perk in active_perks
            var = tk.BooleanVar(value=is_active)
            perk_vars[perk] = var
            cb = ttk.Checkbutton(self.sl_detail_frame, text=display, variable=var)
            cb.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=16, pady=1)
            row += 1

        self.sl_perk_vars[idx] = perk_vars

    def _apply_squad_leaders(self):
        """Write squad leader edits back into save data."""
        if not self.save:
            return

        for idx, stat_vars in self.sl_stat_vars.items():
            sl = self.save.squad_leaders[idx]
            new_stats = []
            for i, var in enumerate(stat_vars):
                try:
                    new_stats.append(float(var.get()))
                except ValueError:
                    name = self.STAT_NAMES[i] if i < len(self.STAT_NAMES) else f"Stat {i+1}"
                    messagebox.showerror("Invalid value",
                                         f"{sl.display_name}: {name} must be a number.")
                    return
            sl.stats = new_stats

        for idx, perk_vars in self.sl_perk_vars.items():
            sl = self.save.squad_leaders[idx]
            # Preserve original order for perks that remain active,
            # then append any newly enabled perks at the end.
            old_set = set(sl.perks)
            new_active = {perk for perk, var in perk_vars.items() if var.get()}
            new_perks = [p for p in sl.perks if p in new_active]  # keep original order
            for perk, var in perk_vars.items():
                if var.get() and perk not in old_set:
                    new_perks.append(perk)
            sl.perks = new_perks


def main():
    app = MenaceEditor()
    app.mainloop()


if __name__ == '__main__':
    main()
