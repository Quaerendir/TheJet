# The Jet (Atari 8-bit, 1992) — conversion pipeline

Clean reconstruction of Dariusz Zolna's *The Jet* as published in
**Tajemnice ATARI 6-7/92** (type-in hex listing). Goal: a faithful,
deterministic engine in Python and a pygame front end, the same method as
[Heartlight](https://github.com/Quaerendir/Heartlight) and
[FAC](https://github.com/Quaerendir/FAC).

Original game: Dariusz Zolna, (C) 1992 Tajemnice ATARI. Conversion
(extraction, disassembly, specification, engine, front end): **Quaerendir**.

A vertically scrolling shooter: the jet flies up an endless trench of
concrete you design yourself in a text editor. Shoot the soft walls, the fuel
tanks, the ammunition dumps and the repair stations, avoid the hard walls and
the tanks patrolling the trench and dropping shells. Three jets, fuel that
runs out, six-digit score, no ending: the board wraps around.

## Files

| file | what |
|------|------|
| `6-7_92_thejet.html` | the magazine article with the listing and the sample board (source: unofficial TA archive, Pixel 2001) |
| `THEJET.LST`, `THEJET.COM`, `THEJET.PLA` | **the references**: the listing, the binary it encodes and the board, from `6-7_92.atr` in the archive's `6-7_92_listingi.zip` |
| `TheJet.bas`, `plansze.txt` | the listing and the board as text taken from the HTML; identical to the LST/PLA (checked by `tests/test_extract.py`) |
| `thejet_extract.py` | stage 1: decodes the hex DATA lines the way *Zgrywus* does, splits the DOS binary, writes the files below |
| `thejet.obj` | the 4157 bytes of the listing = `THEJET.COM` (JET.OBJ of the article) |
| `charset.bin`, `game.bin`, `text.bin` | the three segments: the character set ($2400), the code ($3000), the status line and title texts ($3E43) |
| `board.txt` | the sample board, 142 rows of 16, with a legend |
| `meta.json` | segments, memory map, source provenance |
| `JET.COM` | the playable file = binary + board, as the article's *Append* step makes it; byte-identical to the archive's |
| `thejet.xex` | the same game with the board embedded as a segment (`tools/build_xex.py --standalone`): loads with any loader or emulator |
| `thejet_disasm.py`, `game.asm` | stage 2: recursive-descent disassembler (py65) and the annotated disassembly of `game.bin` |
| `SPEC.md` | engine specification, every rule traced to a label in `game.asm` |
| `thejet/engine.py` | stage 3: the engine, a literal re-implementation of the main loop, `SCAN` and the VBI, with a cycle model of the main loop |
| `tests/test_engine.py` | acceptance tests T1–T12 from `SPEC.md` §9 |
| `tests/test_original.py` | the engine against the original 6502 code running in py65, frame by frame |
| `tools/run_original.py` | boots `JET.COM` in py65 with a minimal OS model (the DOS loader's channel for `INIT`, VBIs, joystick, `RANDOM`) |
| `tools/build_xex.py` | builds `JET.COM` (article layout) or `thejet.xex` (standalone) |
| `tools/atari800_timing.py` | measures the real cadence of the main loop in libatari800 (cycle-exact, ANTIC DMA included) |
| `thejet/data/` | copies of `charset.bin`, `game.bin`, `text.bin`, `board.txt`, `meta.json` shipped inside the package |

## How the original works

Not a BASIC program this time: the listing is 320 lines of hexadecimal digits
that the magazine's *Zgrywus* utility writes verbatim to a file, JET.OBJ — a
DOS binary with a character set, 2.8 KB of 6502 code and the texts. The board
is a separate text file (16 characters per row, `#` hard wall, `"` soft wall,
`%` fuel, `$` ammunition dump, `!` repair, `<` `>` tanks) that the player
appends to it. The trick that makes the merged file work: the binary's INITAD
routine finds the IOCB the DOS loader is reading the file with, reads the rest
of the file — the board — through it, closes the channel and **falls straight
into the game**; it never returns to the loader, and RUNAD points at the same
place for form's sake. Any loader that does not keep a CIO channel open across
INITAD (emulators' built-in loaders, for instance) starts the game with no
board; `thejet.xex` is the same game with the board as a normal segment.

The screen memory is the game state: 24 rows of 32 characters in ANTIC mode
4 (narrow playfield, a board cell is 2×2 characters), the top two rows a
staging area where each new board row is written while the window scrolls
down through the memory one scanline at a time. Tanks, shells, splashes and
explosions are characters, animated by one pass over the memory per
iteration of the main loop — a pass whose in-place, forward-propagating
semantics (a shell dropped by a tank falls two pixels in the same pass; a
character not in the handler table makes the scan skip the next one) the
engine reproduces literally. The jet is two multicolour players, the shots
are the four missiles, and the vertical blank routine moves them, tests the
missiles against the character under them and the jet against the four
characters around it, counts the fuel down (one unit per 32 frames) and
writes the status line. Every detail is in `SPEC.md`.

Two things the code does that the article does not say:

- **The tank rule.** A tank whose right neighbour cell is not empty is not
  placed at all (`LOAD_ROW`; the article warns instead that such a tank
  "erases the left half" of the neighbour). The sample board writes every
  left-facing tank as `<####`: none of its 30 tanks facing left ever appears,
  and the 26 facing right all do. What the player sees in their place is the
  staging rows' stale contents — the top half of the row below, twice.
- **Three frames per iteration.** The main loop waits for the vertical blank,
  scrolls, scans, and if the scan ran into the next frame it waits for the one
  after that. Even an empty board's scan costs 22 222 CPU cycles, about 900
  more than a PAL frame leaves after ANTIC's DMA, the DLIs and the vertical
  blank routines, so on real hardware **every iteration takes three frames**:
  the screen scrolls one scanline (two with the stick pushed up) every 60 ms,
  a tank moves 2 pixels in that time, and the vertical blank interrupts the
  scan somewhere in its last third. Measured in libatari800
  (`tools/atari800_timing.py`), reproduced by the engine's cycle model.

## Verification

- `THEJET.LST` from the archive's disk image equals `TheJet.bas` line for
  line; the decoded DATA equal `THEJET.COM`; `plansze.txt` equals
  `THEJET.PLA`; the merged `JET.COM` equals the archive's (SHA-256 in
  `tests/test_extract.py`).
- `tools/run_original.py` runs the original code in py65: the DOS loader's
  channel and CIO for `INIT`, a vertical blank every PAL frame with the
  joystick, trigger and key shadows, `RANDOM` from a seeded generator, and —
  for the comparison — the option to fire the vertical blank exactly where
  the engine's cycle model put it inside the scan.
- `tests/test_original.py` plays the sample board and two tank boards with
  an autopilot for up to 1500 frames and compares the 800 bytes of screen
  memory, the 28 game variables, the 256 bytes of missile memory and the
  eight POKEY registers after **every frame**. They are identical, including
  the frames in which the vertical blank interrupts the scan half way.
- The engine's count of CPU cycles for `SCROLL` and `SCAN` is checked
  against py65 (within 40 cycles per scan).

## Usage

```
python3 thejet_extract.py TheJet.bas plansze.txt --com JET.COM   # -> thejet.obj charset.bin game.bin text.bin board.txt meta.json JET.COM
python3 tools/build_xex.py --standalone                          # -> thejet.xex
pip install py65
python3 thejet_disasm.py thejet.obj > game.asm
python3 tools/run_original.py JET.COM --frames 600 --dump        # the original in py65
pip install pytest hypothesis mypy
python3 -m pytest -q          # 66 tests
python3 -m mypy thejet/       # strict
```

```python
from thejet import Engine, Input, parse_board
e = Engine(parse_board(open('board.txt').read()))
events = e.tick(Input.of(right=True, fire=True))   # one PAL frame; e.mem, e.state, e.pokey
```

## Open items

- **The cycle budget of a frame is estimated** (`Timing`, `SPEC.md` §7): the
  CPU time between vertical blanks was fitted to libatari800's behaviour on
  the sample board; it decides at which character the vertical blank
  interrupts the scan. The cadence (three frames per iteration) does not
  depend on it.
- Stage 4 (pygame front end, sound) is in progress.
- The magazine's two-letter line codes for this listing were not transcribed
  (the archive states its listings were verified with them).

## License

The conversion (extractor, disassembler, engine, front end, tests, spec) is
released under the MIT licence, see `LICENSE`. The original game and the
material derived from it (`THEJET.*`, `TheJet.bas`, `plansze.txt`, the
article, `thejet.obj`, `JET.COM`, `thejet.xex`, `game.bin`, `charset.bin`,
`text.bin`, `board.txt`, `game.asm`, screenshots) remain (C) 1992 Dariusz
Zolna / Tajemnice ATARI and are included for preservation and study only, see
`NOTICE`.
