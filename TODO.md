# Project Plan

## Save File Analysis
- [x] Reverse-engineer `main.save` binary format
- [x] Document save file structure and field offsets (see ANALYSIS.md)
- [ ] Identify editable values (stats, inventory, progress, etc.) — partially done, global stats need labeling

## Global Stats Identification Checklist

Cross-reference these values in the running game to identify each stat.
Values from two saves shown for comparison (main.save / auto save).

| # | Offset | main | auto | Identified? | Label |
|---|--------|------|------|-------------|-------|
- [ ] 0 | `0x0095` | 18 | 18 | | *(count field — not a game stat)* |
- [ ] 1 | `0x0099` | 0 | 0 | | |
- [x] 2 | `0x009D` | 128,199 | 128,086 | Yes | 'OCI Components' |
- [x] 3 | `0x00A1` | 89,505 | 89,467 | Yes | 'Promotion Points' |
- [ ] 4 | `0x00A5` | 1,416 | 1,378 | | |
- [ ] 5 | `0x00A9` | 12 | 11 | | |
- [ ] 6 | `0x00AD` | 10 | 9 | | |
- [ ] 7 | `0x00B1` | 10 | 10 | | |
- [ ] 8 | `0x00B5` | 3 | 3 | | |
- [ ] 9 | `0x00B9` | 6 | 6 | | |
- [ ] 10 | `0x00BD` | 6 | 6 | | |
- [ ] 11 | `0x00C1` | 2 | 2 | | |
- [ ] 12 | `0x00C5` | 50 | 50 | | |
- [ ] 13 | `0x00C9` | 0 | 0 | | |
- [x] 14 | `0x00CD` | 9 | 9 | Yes | 'Intelligence' |
- [ ] 15 | `0x00D1` | 0 | 0 | | |
- [x] 16 | `0x00D5` | 100 | 90 | Yes | 'Authority' |
- [ ] 17 | `0x00D9` | 812 | 699 | | |
- [ ] 18 | `0x00DD` | 0 | 0 | | |
- [ ] 19 | `0x00E1` | 42 | 42 | | |

## Open Questions
- [ ] What does the `trail_value` on characters represent? (XP, mission count, or something else?)
- [x] Obtain a second save file with a different game state to compare field values

## Core Library
- [x] Implement save file parser (read)
- [x] Implement save file writer (write modified data)
- [ ] Add validation to prevent corrupted saves

## Editor Interface
- [x] Build CLI for viewing save data
- [x] Build CLI for editing save values
- [x] Add backup creation before modifying saves

## Testing
- [ ] Set up test framework
- [ ] Add tests for parsing known save files
- [ ] Add round-trip tests (read → write → read produces same data)

## Packaging
- [ ] Add `pyproject.toml` with project metadata
- [ ] Add usage instructions to README
