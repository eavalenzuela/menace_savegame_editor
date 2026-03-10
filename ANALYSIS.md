# MENACE Save File Format Analysis

Analysis of `main.save` (47,283 bytes). All multi-byte integers are **little-endian**. Strings are **length-prefixed** with a single byte indicating length (max 255 chars), encoded as UTF-8.

---

## Section Map

| Offset Range | Section | Description |
|---|---|---|
| `0x0000–0x0094` | [Header](#header) | Version, location, difficulty, timestamps |
| `0x0095–0x00E4` | [Global Stats](#global-stats) | Turn counter, resources, currencies |
| `0x00E5–0x0567` | [OCI Modules](#oci-modules-orbital-command-infrastructure) | Installed and available ship modules |
| `0x0568–0x05AB` | [Resource Counters](#resource-counters) | Per-resource tallies (purpose unclear) |
| `0x05AC–0x0669` | [Player Vehicles](#player-vehicles) | Owned vehicles with health values |
| `0x066A–0x5D03` | [Item Catalog](#item-catalog) | All known items: accessories, armor, weapons, blueprints, commodities, vehicle parts, etc. |
| `0x5D04–0x5F82` | [Story Factions](#story-factions) | Faction discovery status and associated OCI modules |
| `0x5F83–0x6CBA` | [Player Character Roster](#player-character-roster) | 67 player-side characters |
| `0x6CBB–0x7403` | [Captured/Enemy Roster](#capturedenemy-character-roster) | 25 captured or encountered enemy characters |
| `0x7404–0x742F` | [Roster Epilogue](#roster-epilogue) | Final faction tag + sentinel bytes |
| `0x7430–0x96FF` | [Squad Leaders](#squad-leaders) | Detailed stats, perks, equipment, and history for each squad leader/pilot |
| `0x9700–0xA650` | [Campaign & Operations](#campaign--operations) | Planet state, operation progress, completed/running operations |
| `0xA650–0xADF0` | [Missions](#missions) | Individual mission data: objectives, weather, status |
| `0xADF0–0xB557` | [Dialogue Flags](#dialogue-flags) | Named flags tracking which dialogue/bark events have played |
| `0xB558–0xB800` | [Events](#events) | Story and system map event triggers |
| `0xB800–0xB8B3` | [Offmap Abilities](#offmap-abilities) | Available orbital strike / support abilities |

---

## Header

| Offset | Type | Example Value | Field |
|---|---|---|---|
| `0x0000` | u32 | `102` | Save format version |
| `0x0004` | u32 | `1` | Unknown (possibly save slot index) |
| `0x0008` | 8 bytes | `0713c1b3bc7bde08` | Hash or random seed |
| `0x0010` | string | `"The Backbone"` | Current planet/location |
| varies | string | `"Thwart Invasion"` | Current operation name |
| varies | u32 | `0` | Unknown |
| varies | u32 | `4` | Unknown |
| varies | string | `"global_difficulty.normal"` | Difficulty setting |
| varies | string | `"strategy_config"` | Config identifier |
| varies | f64 | `80482.98...` | Timestamp (game-internal clock) |
| varies | string | `"main"` | Save slot name |
| varies | f64 | `80482.98...` | Timestamp (duplicate or last-modified) |
| varies | 5 bytes | `00 00 87 14 28` | Unknown (flags or packed data) |
| varies | u8 + u8 | `00 01` | Unknown separator |
| varies | string | `"global_difficulty.normal"` | Difficulty (repeated) |

## Global Stats

Starting at `0x0095` (offset depends on header string lengths):

| Offset | Type | Value | Likely Meaning |
|---|---|---|---|
| `0x0095` | u32 | `18` | Turn/day counter (?) |
| `0x0099` | u32 | `0` | Unknown |
| `0x009D` | u32 | `128,199` | Large resource (money? XP?) |
| `0x00A1` | u32 | `89,505` | Large resource |
| `0x00A5` | u32 | `1,416` | Medium resource |
| `0x00A9` | u32 | `12` | Stat (days in current operation?) |
| `0x00AD` | u32 | `10` | Stat |
| `0x00B1` | u32 | `10` | Stat |
| `0x00B5` | u32 | `3` | Stat |
| `0x00B9` | u32 | `6` | Stat |
| `0x00BD` | u32 | `6` | Stat |
| `0x00C1` | u32 | `2` | Stat |
| `0x00C5` | u32 | `50` | Stat (authority? morale?) |
| `0x00C9` | u32 | `0` | Stat |
| `0x00CD` | u32 | `9` | Stat |
| `0x00D1` | u32 | `0` | Stat |
| `0x00D5` | u32 | `100` | Stat (max morale? reputation?) |
| `0x00D9` | u32 | `812` | Stat (OCI points? spare parts?) |
| `0x00DD` | u32 | `0` | Stat |
| `0x00E1` | u32 | `42` | Stat (total missions? kills?) |

> **Note:** The exact meaning of these stats is unknown. Cross-referencing with in-game values from multiple saves would be needed to identify them (money, authority, morale, OCI points, spare parts, supplies, etc.).

## OCI Modules (Orbital Command Infrastructure)

Starting at `0x00E5`. The first byte is a count (`10` = 0x0A), followed by that many length-prefixed strings of **installed** OCI module IDs.

**Format:** `count(u8?)` then `count` entries of: `marker(u8=0x01)` + `string(module_id)`

Example modules:
- `oci.dice_informants_hub`
- `oci.zayn_auto_laser_sentry_turret`
- `oci.standard_unguided_missile_strike`
- `oci.unbent_advanced_medical_bay`

There appear to be multiple lists: installed modules (active), available modules (unlocked), etc. Each prefixed with a count.

## Resource Counters

Around `0x0568–0x05AB`: A series of u32 values, purpose not fully determined. These may represent per-item-category inventory counts or resource subtotals.

## Player Vehicles

Starting around `0x05AC` with a count prefix.

**Per-vehicle entry:**
| Field | Type | Example |
|---|---|---|
| Vehicle type | string | `"player_vehicle.modular_light_troop_carrier"` |
| Instance UUID | string (36 chars) | `"c0596615-974e-408c-90af-00bbb44f4fda"` |
| Health 1 | f32 | `1.0` |
| Health 2 | f32 | `1.0` |
| Unknown | u32 | `0` |

Three vehicles in this save.

## Item Catalog

`0x066A–0x5D03` — The largest section. Contains all known item types organized by category:

- **Accessories** (`accessory.*`): ammo types, grenades, equipment, drugs, vehicle accessories
- **Armor** (`armor.*`): player and enemy armor sets
- **Weapons** (`weapon.*`): assault rifles, SMGs, battle rifles, special weapons
- **Special Weapons** (`specialweapon.*`): heavy weapons, tripod-mounted weapons, sniper rifles
- **Blueprints** (`blueprint.*`): craftable item blueprints
- **Commodities** (`commodity.*`): trade goods, crafting materials, faction-specific loot
- **Turrets** (`turret.*`): vehicle/construct turret types
- **Mod Weapons** (`mod_weapon.*`): vehicle weapon modules (light/medium/heavy)
- **Vehicle Chassis** (`vehicle.*`): available vehicle types
- **Dossiers** (`dossier.*`): squad leader and pilot dossiers
- **Blueprint Vouchers** (`blueprint_voucher.*`): tier 1/2/3
- **Vouchers** (`voucher.*`): OCI points, authority

Each item entry consists of:
- Item type ID (string)
- Instance UUID (string, 36 chars) — present only for owned instances
- Some items have multiple UUIDs (multiple copies owned)

Items are grouped: first a batch of type IDs (the "catalog" of known items), then followed by instance entries with UUIDs representing actual owned copies. Some entries have quality tags: `Base`, `Regular`, `Tagged`, `SpecialOffer`.

## Story Factions

Starting around `0x5D04`. Lists factions and their discovery state.

**Per-faction entry:**
| Field | Type | Example |
|---|---|---|
| Faction ID | string | `"story_faction.dice"` |
| Discovery count(?) | u8/u32 | varies |
| Status | string | `"Known"` or `"Unknown"` |
| Associated OCI modules | string[] | list of `oci.*` module IDs |
| Module stats | u16[] | numeric values per module |

Known factions in this save:
- `story_faction.dice` — Known
- `story_faction.firan` — Unknown
- `story_faction.jingwei` — Unknown
- `story_faction.lurchen` — Unknown
- `story_faction.tolimen` — Unknown
- `story_faction.unbent` — Known
- `story_faction.zayn_beecher` — Known

## Player Character Roster

**Offset:** `0x5F83`
**Count:** u32 = `67`

**Per-character entry:**
| Field | Type | Example |
|---|---|---|
| Marker | u8 | `0x01` (always) |
| Character ID | u8 | `8`, `13`, `19`, ... |
| Padding | 3 bytes | `00 00 00` |
| Gender | string | `"Male"` or `"Female"` |
| Skin color | string | `"Black"`, `"White"`, `"Brown"` |
| Origin | string | `"Earth"`, `"Mars"`, `"Proxima"`, `"TheMoon"`, `"Efio13"`, `"Kentaurus"` |
| Full name | string | `"Stan Traynor"` |
| Nickname | string | `"Problem"` |

**Between entries:** `trail_value(u32)` + `has_faction(u8=0x00)`

The `trail_value` likely represents the character's experience, mission count, or similar progression metric. Higher values correlate with characters listed earlier (veterans).

## Captured/Enemy Character Roster

**Offset:** `0x6CBB`
**Count:** u32 = `25`

Same format as player roster, but entries may include a **faction string** before the character data:

**Entry with faction:**
`trail_value(u32)` + `has_faction(u8=0x01)` + `faction_string` + `0x01` + `id(u8)` + `000000` + 5 strings

**Faction types seen:**
- `enemy.pirate_outcasts`
- `enemy.pirate_scavengers`
- `enemy.pirate_boarding_commandos`
- `enemy.pirate_chaingun_team`
- `enemy.rogue_army_autocannon_weapon_team`
- `enemy.rogue_army_sniper_team_jaeger`
- `enemy.alien_harpy`
- `enemy.alien_acid_spitter_bombardier`
- `enemy.pirate_vehicle.heavy_mg_heavy_truck`

Some captured characters have no faction (e.g., defectors or recruited neutrals).

## Roster Epilogue

After the last captured character entry at `0x7404`:
- Final `has_faction(0x01)` + faction string
- Sentinel: `0x01 0xFFFF` followed by 14 bytes (hash/identifier)
- Then `u32(8)` introducing the squad leader section

## Squad Leaders

Starting around `0x7430`. Each squad leader entry contains:

| Field | Type | Description |
|---|---|---|
| Class | string | `"Infantry"` or `"Vehicle"` |
| Leader ID | string | `"squad_leader.darby"`, `"pilot.rewa"`, etc. |
| Stat count | u32 | `7` |
| Stats | f32[] | 7 float values (likely: accuracy, toughness, leadership, morale, etc.) |
| Perk count | u32 | `8` |
| Perks | string[] | Length-prefixed perk IDs |
| Equipment | mixed | UUIDs referencing item instances from the catalog |
| Mission history | mixed | Counts, relationship data, emotional states |
| Status | string | `"Alive"` |
| Known squad leaders | string[] | List of other leaders this one has served with |
| Emotional state | string | Optional, e.g. `"emotional_state.euphoric"`, `"emotional_state_injuries.bruised"` |

**Known squad leaders in this save:**
- `squad_leader.darby` (Infantry) — 7 stats, 8 perks
- `squad_leader.pike` (Infantry) — unique perks
- `pilot.rewa` (Vehicle) — vehicle pilot
- `squad_leader.carda` (Infantry)
- `squad_leader.wetteroth` (Infantry)
- `pilot.exconde` (Vehicle)
- `squad_leader.greifinger` (Infantry)
- `pilot.ivey` (Vehicle)

**Stat values** are f32 ranging roughly 0–100, likely representing skills/attributes:
- Example (Darby): `[89.9, 84.7, 71.9, 53.4, 43.5, 33.9, 77.2]`

## Campaign & Operations

Starting around `0x9700`. Contains:

**Planets:**
- `planet.backbone`
- `planet.dice`
- `planet.mock`

**Operations** with structure:
| Field | Type | Example |
|---|---|---|
| Operation ID | string | `"operation.pirates_thwart_invasion"` |
| Faction | string | `"story_faction.dice"` |
| Enemy faction | string | `"faction.pirates"` |
| Duration | string | `"operation_duration.long"` |
| Status | string | `"Completed"` or `"Running"` |
| Difficulty | string | `"mission_difficulty_normal"` |
| Rewards | f32 + mixed | Score, loot items |
| Squad composition | string[] | Which leaders were assigned |
| Performance metrics | f32[] | Per-squad-leader scores |

## Missions

Starting around `0x9F6E`. Each mission includes:

| Field | Type | Example |
|---|---|---|
| Mission ID | string | `"mission.pirates_secure_repair_depot"` |
| Phase | string | `"First"`, `"Middle"`, `"Final"` |
| Difficulty | string | `"mission_difficulty_normal"`, `"_hard"`, `"_final"` |
| Faction | string | `"story_faction.dice"` |
| Score values | f32 | Mission rating |
| Time of day | string | `"Day"` |
| Weather | string | `"weather.snow_light_snowfall"`, `"weather.snow_snowstorm"` |
| Biome | string | `"biome.snow"`, `"biome.temperate_forest"` |
| Special conditions | string | `"fuel_shortage"`, `"casevac_facilities"`, etc. |
| Play status | string | `"Played"`, `"Playable"`, `"Locked"`, `"Unplayable"` |
| Objective statuses | string[] | `"Completed"`, `"Ongoing"`, `"Failed"`, `"Aborted"` |

## Dialogue Flags

Around `0xADF0–0xB557`. A count-prefixed list of named string flags tracking which dialogue events have played:

Examples:
- `arrival_slname_2_played`
- `click_bark_rewa`
- `success_darby_3_played`
- `rogue_army_ops_unlocked`
- `pirate_heavies_introduce_themselves_played`

## Events

`0xB558–0xB800`. Story and system map events with play state:

| Field | Type | Example |
|---|---|---|
| Marker | u8 | `0x01` |
| Event path | string | `"Story/event_email_black_market"` |
| State | u32 | `1` (played/triggered) |

Event categories:
- `Story/event_*` — narrative events
- `SystemMap/event_*` — random/map events

## Offmap Abilities

`0xB838–0xB8B3` (near end of file). A short list of available orbital/offmap support abilities:

- `offmap_ability.unguided_missle_strike` (note: typo "missle" is in the game data)
- `offmap_ability.auto_laser_sentry_turret` (appears twice = 2 charges?)

---

## General Encoding Rules

1. **Strings**: 1-byte length prefix + UTF-8 content. Max length 255.
2. **Integers**: Little-endian u32 unless otherwise noted.
3. **Floats**: IEEE 754 f32 (4 bytes) for stats/health, f64 (8 bytes) for timestamps.
4. **UUIDs**: Stored as 36-character strings (with dashes), length-prefixed like all strings.
5. **Lists**: Typically preceded by a u32 count.
6. **Markers**: `0x01` bytes frequently used as entry separators/presence flags.
7. **Character rosters**: Use `has_faction(u8)` between entries: `0x00` = no faction, `0x01` = followed by faction string.

## Open Questions

- [ ] Exact identity of the 15 global stat values at `0x00A9` (money, authority, morale, OCI points, spare parts, supplies, etc.)
- [ ] Detailed structure of squad leader equipment slots and mission history
- [ ] Whether the `trail_value` on characters represents XP, missions completed, or something else
- [ ] Purpose of the 14-byte blob after the `0xFFFF` sentinel
- [ ] Exact structure of the item catalog section (how item ownership/quantity is tracked)
- [ ] Structure of the resource counters section (`0x0568–0x05AB`)
- [ ] Whether additional saves with different game states would reveal fixed vs. variable offsets
