# The Jet — Game Engine Specification (derived from the disassembly)

Target: pure-logic engine module in Python 3.11+ (stage 3, `thejet/engine.py`),
no rendering, no I/O. Rendering, sound and input (pygame) are stage 4 and
consume the engine through the API in §8.

Original: Dariusz Zolna, 1992, Atari 8-bit, machine code, published as a hex
listing for the magazine's *Zgrywus* utility in Tajemnice ATARI 6-7/92
(`6-7_92_thejet.html`). The reference is `THEJET.COM` from the archive's disk
image, byte-identical to what the listing encodes (`thejet.obj`). Every rule
below was read from the 6502 code in `game.asm` (labels in `CAPITALS` refer to
that file) and, where it says so, confirmed by running the original in py65
(`tools/run_original.py`). Nothing is guessed except the CPU time budget of a
frame (§7), marked **[EST]**.

---

## 1. Data model

### 1.1 The screen memory is the game state
ANTIC mode 4, narrow playfield: **32 characters per row**, a board cell is a
2×2 block of characters, so the 16-column board is 32 characters wide. The
game keeps 24 character rows of 32 bytes from `SCREEN` = $3B43:

| rows | address | role |
|------|---------|------|
| −2, −1 | $3B43, $3B63 | staging area: the next board row is loaded here (§3.3) |
| 0 … 19 | $3B83 … $3DE3 | displayed, fine-scrolled by `VSCROL_CTR` (§3.1, §10) |
| 20, 21 | $3E03, $3E23 | below the window, blanked at every shift (§3.2) |
| (22) | $3E43 | the status line `HUD`, 32 bytes, ANTIC mode 2 (§5.9) |

Everything that moves on the playfield — tanks, shells, splashes, explosions —
is a character written into this memory and animated by rewriting it (§4).
The engine therefore keeps exactly this: `mem`, 800 bytes = 24 rows × 32 plus
the 32-byte status line, index `(row + 2) * 32 + col`. Pointer arithmetic in
the original (`SCAN_PTR ± 1`, `+$20`, `+$21`, `+$41`, …) is plain index
arithmetic on this array and **crosses row boundaries the same way** (the
last column's right neighbour is the next row's first column). The only
objects outside this memory are the jet and its shots (§1.4).

### 1.2 Character codes (the redefined charset, `charset.bin`, CHBAS = $24)
| code | what | placed by |
|-----:|------|-----------|
| $00 | empty | — |
| $01 $02 / $03 $04 | hard wall `#` (top-left, top-right / bottom-left, bottom-right) | `LOAD_ROW` |
| $05 $06 / $07 $08 | soft wall `"` | `LOAD_ROW` |
| $09 $0A / $0B $0C | fuel `%` | `LOAD_ROW` |
| $0D $0E / $0F $10 | ammunition dump `$` | `LOAD_ROW` |
| $11 $12 / $13 $14 | repair `!` | `LOAD_ROW` |
| $15/$16, $17/$18, $19/$1A, $1B/$1C, $1D/$1E | a shell dropped by a tank: the top character shows the shell 0, 2, 4, 6, 8 pixels down, the character below it the rest (§4.5) | `H_TANK_DROP` |
| $1F … $23 | splash animation, five frames (§4.6) | `HIT_HARD`, `SH_SPLASH` |
| $24 $25 / $26 $27, then $28…, $2C…, $30…, $34…, $38…, $3C… | explosion, seven 2×2 frames (§4.7) | `PUT_EXPLOSION` |
| $48 $49 $4A / $68 $69 $6A | tank facing right, phase 0 (three columns: body, body, blank) | `LOAD_ROW` (two columns only), `DRAW_TANK` |
| $4B $4C $4D / $6B…, $4E $4F $50 / $6E…, $51 $52 $53 / $71… | the same tank 2, 4, 6 pixels to the right (phases 1–3) | `DRAW_TANK` |
| $54 $55 $56 / $74 $75 $76 | tank facing left, phase 0: blank, body, body (the body sits in the **right** two columns) | `LOAD_ROW` (two columns only), `DRAW_TANK` |
| $57…, $5A…, $5D… | the same tank 2, 4, 6 pixels to the left (phases 1–3) | `DRAW_TANK` |

The two tank sprites are the same picture; "facing" is only the direction of
travel. Codes not listed ($40–$47, $60–$67 and the tails of the ranges above)
are blank glyphs or unused.

### 1.3 The board
A text file: rows of 16 characters separated by ATASCII EOL ($9B), no EOL
after the last row. The game reads it into `BOARD` = $3F25 through the DOS
loader's channel (`INIT`, §6.1) and remembers `BOARD_END` = the address of the
**last** row. Play starts at the last row of the file and proceeds upwards
through the file; after the first row the pointer wraps to the last row again
(`LR_WRAP`): **the board is endless**.

Row characters, `TILE_CHARS` (`LR_MATCH` compares entries 7..1): `#` `"` `%`
`$` `!` `<` `>`; **any other character is empty**.

### 1.4 The jet and the shots (player/missile graphics)
The jet is players 0 and 1 (multicolour, 13 lines each, `JET_SHAPE0/1`) at
vertical position $B0, horizontal `JET_X` ∈ [$40, $B9] (`VB_STICK`). The shots
are the four missiles, `MISSILE_X[4]` (0 = slot free) and `MISSILE_Y[4]`,
drawn two pixels tall into the missile memory `MISSILES` ($2B00, §5.4) as the
fifth player. Player/missile coordinates map to characters by `CELL_ADDR`:

```
col = (x − 63) >> 2            (4 colour clocks per character)
row = ((y − 41) >> 3) − 1      (relative to row −1, i.e. row index −1 for y = 41..48)
```
(`CELL = ROW_M1 + ((y−41) & ~7) * 4 + ((x−63) >> 2)`.) The fine scroll is not
part of the formula: the collision box is up to 7 scanlines off the picture.

### 1.5 Variables (`VAR_UNUSED` … `PAUSED`, $3989–$39A4, zeroed by `GI_VARS`)
| original | engine | meaning |
|----------|--------|---------|
| `VSCROL_CTR` $398A | `vscrol` | fine scroll 7..0 (§3.1); 0 after `GI_VARS`, so the first iteration shifts at once |
| `ROW_TOGGLE` $398B | `row_toggle` | a board row is loaded every second shift |
| `PARITY` $398C | `parity` | flips after every scan; explosions advance when it is 0 before the flip |
| `FLASH` $398D | `flash` | frames left of the hit flash / invulnerability (50) |
| `SND_SHELL`, `SND_SPLASH`, `SND_SHOT`, `SND_DEATH` $398E–$3991 | `snd_*` | sound envelopes (§5.1) |
| `JET_X` $3992 | `jet_x` | $70 at start |
| `MISSILE_X/Y` $3993/$3997 | `missile_x[4]`, `missile_y[4]` | y is 0 at start (`GI_MISSILES` stores $2F then 0) |
| `TRIG_PREV` $399B | `trig_prev` | STRIG0 of the previous frame |
| `DEATH` $399D | `death` | set by the VBI, consumed by the main loop |
| `FUEL` $399E/$399F | `fuel` | BCD, three digits, 099 at start |
| `JETS` $39A0 | `jets` | spare jets, 2 at start |
| `SCORE` $39A1–$39A3 | `score` | BCD, six digits |
| `PAUSED` $39A4 | `paused` | $FF while paused |

---

## 2. Frame model

One PAL frame = one VBI + (usually) one iteration of the main loop:

```
VBI  (deferred vertical blank, VBI, §5): sounds; if not paused: joystick → JET_X,
     fire, missiles, missile hits, jet collision, fuel, HUD, TRIG_PREV
MAIN_LOOP: wait for RTCLOK to change (= the VBI above)
     ESC → FADE_OUT and the title screen; space → PAUSE (§6.3)
     SCROLL (§3), SCAN (§4)              ← ML_FRAME
     jet colours (normal or flashing), FLASH−−
     DEATH? → lose a jet or game over (§6.2)
```
The main loop would run once per frame if `SCROLL`+`SCAN` finished before
the next VBI; they never do (§7). `ML_FRAME` remembers `RTCLOK+1` before the
scan; when the scan ends in the next frame the loop waits for the frame after
that (`ML_WAIT_SCAN`), and `MAIN_LOOP` then waits for yet another RTCLOK
change: **every iteration takes three frames**, during which the VBI runs
three times — the second one in the middle of the scan (or, on the iterations
that shift and load a row, both the second and the third). `tick(inp)` in the
engine = the VBI followed by as much of the main loop as the frame's CPU
budget allows (§7, §8).

The order inside a frame matters: the VBI sees the grid as the previous
iteration left it; the iteration sees `JET_X`, the missiles and `DEATH` as the
VBI just set them.

Inputs per frame: joystick `STICK0` (bit 0 up, bit 2 left, bit 3 right, active
low; bit 1 down is unused), trigger `STRIG0` (0 = pressed), key code `CH`
($1C ESC, $21 space; the OS leaves a code in `CH` until the game clears it,
which it does only on unpause and at `GAME_INIT`).

---

## 3. Scrolling and loading rows (`SCROLL`, `LOAD_ROW`)

### 3.1 Fine scroll (`SCROLL`)
```
VSCROL_CTR −= 1;  if STICK0 up: VSCROL_CTR −= 1 again    (2 scanlines per iteration)
VSCROL = VSCROL_CTR
if VSCROL_CTR < 0:  VSCROL_CTR = VSCROL = 7; SC_SHIFT (§3.2)
```
The window moves down the memory by one scanline per iteration (§10), i.e.
the picture moves **down** the screen: the jet flies up the board.

### 3.2 Shift (`SC_SHIFT`, `SC_CLEAR_BOTTOM`, `SC_TOGGLE`)
Rows −2..18 are copied to rows −1..19 (row 19's old content is lost, row −2
keeps a stale copy of itself), rows 20 and 21 are zeroed, `ROW_TOGGLE ^= $FF`,
and when it is 0 after the flip `LOAD_ROW` runs. So a row is loaded on every
second shift, into the staging rows that the two previous shifts have just
vacated: consecutive board rows appear without gaps. `GI_VARS` leaves
`ROW_TOGGLE` = 0 and `GAME_INIT` calls `LOAD_ROW` once for the bottom row.

### 3.3 Loading a row (`LOAD_ROW`)
`ROW_PTR` points at the row to load (initially `BOARD_END`, the last row).
```
if byte 15 of the row is EOL ($9B): ROW_PTR −= 1          (rows are 16 bytes + EOL, the pointer
                                                          steps 16, this corrects it; also tolerates
                                                          an EOL after the last row)
for cell = 15 down to 0  (X = 2*cell+1):
    tile = TILE_CHARS index of row[cell], 0 if none
    if TILE_TL[tile] >= $48 (a tank) and mem[row −2][2*cell + 2] != 0: skip this cell
    mem[row −2][2*cell] = TILE_TL[tile]; mem[row −2][2*cell+1] = TILE_TR[tile]
    mem[row −1][2*cell] = TILE_BL[tile]; mem[row −1][2*cell+1] = TILE_BR[tile]
ROW_PTR −= 16;  if ROW_PTR < BOARD: ROW_PTR = BOARD_END
```
`TILE_TL/TR/BL/BR` per tile: empty 0/0/0/0; `#` 01 02 03 04; `"` 05 06 07 08;
`%` 09 0A 0B 0C; `$` 0D 0E 0F 10; `!` 11 12 13 14; `<` 54 55 74 75; `>` 48 49
68 69.

**The tank rule** (`LR_TILE`, confirmed in py65): a tank is not placed when the
top-left character of the cell to its right is non-zero. Cells are filled from
right to left, so that character is what this load just wrote for the right
neighbour — for cell 15 it is row −1's first character, i.e. whatever the
previous load left in the bottom-left of cell 0. A skipped cell keeps the
staging rows' stale contents: after two shifts both staging rows hold the
**top** half of the previously loaded row, so the cell shows that top half
twice. The article warns that a tank touching an element on its right
"erases the left half of that element"; the published code skips the tank
instead. In the article's own board every `<` is followed by `#` (30 of
them) and every `>` by a space (26): **no tank facing left ever appears
there**.

A tank is placed as two columns only ($48 $49 or $54 $55); its third column
($4A blank, or $56 the body's right half) is drawn by the first `DRAW_TANK`.

---

## 4. The object scan (`SCAN`)

Once per iteration, every character of rows −1..19 (`SCAN_PTR` from $3B63 to
$3E02) in memory order:
```
c = mem[SCAN_PTR]
if c >= $15:
    X = index of c in SCAN_CHARS[27..1], 0 if absent
    SCAN_HANDLERS[X](SCAN_PTR)           (may move SCAN_PTR)
SCAN_PTR += 1
```
`SCAN_CHARS` (index 1..27): $48 $4B $4E $51 → `H_TANK_R`; $54 $57 $5A $5D →
`H_TANK_L`; $7A $6E → `H_TANK_DROP`; $15 $17 $19 $1B $1D → `H_SHELL`; $1F $20
$21 $22 $23 → `H_SPLASH`; $24 $28 $2C $30 $34 $38 $3C → `H_EXPLOSION`. Entry 0
($1C) is never compared. Index 0 runs `NEXT_CHAR` (`SCAN_PTR += 1`): **a
character ≥ $15 that is not in the table makes the scan skip the character
after it** (tank body columns $49, $4C…, shell bottoms $16…, explosion
partners $25…; e.g. a shell top at $1D followed by another object in the
next column). Handlers that end in `NEXT_CHAR` (`H_TANK_DROP` after a drop,
`H_EXPLOSION`) also skip one extra character. Row −2 is not scanned, so an
object freshly loaded there waits for the next shift; row 20 is not scanned,
so a shell that moved into it stays until the next shift clears it. Reads and
writes at `+$20`, `+$21`, `+$40`, `+$41` from row 19 land in rows 20–21 (and
from column 31 in the next row's first columns); nothing reaches the status
line from a scanned row, but `mem` includes it so that the engine cannot go
out of range.

After the scan `PARITY ^= $FF`.

### 4.1 `DRAW_TANK(base, offset)` and `PUT3`
Writes `base, base+1, base+2` at `SCAN_PTR + offset` and `base+$20 …` one row
below (`PUT3` twice). Three columns, two rows.

### 4.2 Tank facing right (`H_TANK_R`, on $48 $4B $4E $51)
```
c = mem[p]
if c + 3 < $54:  DRAW_TANK(c + 3, 0); return                 (next phase, 2 px right)
# phase 3 → a full character to the right
if mem[p+3] != 0 or mem[p+$23] != 0:  DRAW_TANK($54, 0); return      (blocked: becomes a tank
                                                                     facing left, in place)
mem[p] = mem[p+$20] = 0;  p += 1 (SCAN_PTR too);  DRAW_TANK($48, 0)
```
So a tank travels 2 px per iteration and one character per 4; the column it
checks before stepping is the one beyond its blank third column; only its own
two rows are checked. A blocked tank turns round without moving.

### 4.3 Tank facing left (`H_TANK_L`, on $54 $57 $5A $5D)
```
c = mem[p]
if c + 3 < $60:  DRAW_TANK(c + 3, 0); return                 (next phase, 2 px left)
p −= 1 (SCAN_PTR too)
if mem[p] != 0 or mem[p+$20] != 0:  p += 1; DRAW_TANK($48, 0); return   (blocked: faces right)
mem[p+3] = mem[p+$23] = 0;  DRAW_TANK($54, 0)
```
Note the asymmetry: the right-facing tank checks the column beyond its
group **before** clearing its old column; the left-facing one moves its
pointer first, and when blocked steps the pointer back and redraws a
right-facing phase 0 over the same three columns.

### 4.4 Dropping a shell (`H_TANK_DROP`, on $6E and $7A)
These are the bottom-left characters of a tank in phase 2 (the tank straddles
the boundary between its columns 1 and 2). Each iteration such a character is
scanned:
```
if RANDOM & 7 != 0: return                     (one read of RANDOM per scan of the character)
if mem[p+$21] != 0 or mem[p+$41] != 0: return  (the two characters below the middle column)
mem[p+$21] = $15; mem[p+$41] = $16; SND_SHELL = 1; NEXT_CHAR
```
`RANDOM` is POKEY's noise register: the engine takes it from an injected
generator (`rnd(): int` 0..255), read exactly once per scanned $6E/$7A.

### 4.5 A falling shell (`H_SHELL`, on $15 $17 $19 $1B $1D)
```
c = mem[p]
if c + 2 < $1E:  mem[p] = c + 2; mem[p+$20] = c + 3; return    (2 px down: 15/16 → 17/18 → … → 1D/1E)
# past the last frame: a full row down
if mem[p+$40] != 0:  mem[p+$20] = $1F; mem[p] = 0; SND_SPLASH = 15; return   (splash where it hit)
mem[p+$20] = $15; mem[p+$40] = $16; mem[p] = 0
```
The shell is scanned again in the same iteration when it moves down (the scan
has not reached `p+$20` yet) — after a row step it advances one more phase in
the same pass; when it hits, the splash at `p+$20` also animates in the same
pass. Reproduce the in-place, forward-propagating scan literally.

### 4.6 Splash (`H_SPLASH`, on $1F … $23)
`mem[p] += 1`, and when the result would be $24 the character becomes 0.
One frame per scan.

### 4.7 Explosion (`H_EXPLOSION`, on $24 $28 $2C $30 $34 $38 $3C)
```
if PARITY != 0:  NEXT_CHAR; return                      (every other iteration only)
f = index of c in EXPL_FRAMES ($24 $28 $2C $30 $34 $38 $3C), +1
if f == 7:  mem[p] = mem[p+1] = mem[p+$20] = mem[p+$21] = 0
else:       b = EXPL_FRAMES[f]; mem[p] = b; mem[p+1] = b+1; mem[p+$20] = b+2; mem[p+$21] = b+3
NEXT_CHAR
```
Seven frames two iterations each: 14 iterations, then the 2×2 is cleared.

---

## 5. The vertical blank routine (`VBI`)

`VSCROL` is rewritten from `VSCROL_CTR` (hardware only), attract mode is
reset, then:

### 5.1 Sounds (every frame, even when paused)
Four POKEY channels driven by four counters; the engine records the eight
register values written each frame (`pokey`, §8):
- **channel 1, shell dropped** (`SND_SHELL`, set to 1 by `H_TANK_DROP`): while
  ≠ 0: `AUDC1 = SND_SHELL` (17-bit noise, volume 1..9), `AUDF1 = 10`,
  `SND_SHELL += 1`; when it reaches 10: `SND_SHELL = 0`, `AUDF1 = AUDC1 = 0`.
- **channel 2, splash / explosion** (`SND_SPLASH`, set to 15 by a missile hit,
  10 by a hard-wall hit, 15 by a shell splash): on odd frames (`RTCLOK & 1`)
  while ≠ 0: `AUDC2 = $20 | v`, `AUDF2 = v + $DC`, `v −= 1`; at 0: both 0.
- **channel 3, shot** (`SND_SHOT`, set to $B0 by a shot): while ≠ 0:
  `AUDF3 = v`, `AUDC3 = $E0 | ((v − $30) >> 3)`, `v −= 1`; at 0: both 0. A hit
  sets it to 0 at once. (Rising pitch; the volume nibble comes from the
  8-bit `(v − $30) >> 3`, so it is 0 at $B0, 15 at $AF … and wraps below $30.)
- **channel 4, jet hit** (`SND_DEATH`, set to 15 by `ML_LOSE_JET`): on frames
  with `RTCLOK & 3 == 0` while ≠ 0: `AUDC4 = $C0 | v` (4-bit noise), `AUDF4 =
  10`, `v −= 1`; at 0: both 0.

### 5.2 Pause
If `PAUSED`: nothing more this frame (`VB_PAUSED` → `VBI_IDLE`).

### 5.3 Joystick (`VB_STICK`)
Right: `JET_X += 1` if `< $B9`. Left: `JET_X −= 1` if `≠ $40`. Both tested
independently, right first. Up is read by `SCROLL` (§3.1), down is unused.

### 5.4 Fire and the missiles (`VB_FIRE`, `VB_MISSILES`)
```
if STRIG0 == 0 and TRIG_PREV != 0:                 (the frame the trigger goes down)
    slot = the highest Y in 3..0 with MISSILE_X[Y] == 0, else none
    if slot: MISSILE_X[slot] = JET_X + 2; MISSILE_Y[slot] = $B0; SND_SHOT = $B0
             (HIT_CHAR is loaded with the character under the new missile and
              tested, but both branches continue: VB_UNREACHED is dead code)
HPOSP0 = HPOSP1 = JET_X
missile memory y = $29..$D8 cleared
for X = 3 down to 0:
    HPOSM[X] = MISSILE_X[X]; MISSILE_Y[X] −= 1; y = MISSILE_Y[X]
    missile memory [y−1] = missile memory [y] = MISSILE_MASKS[X]   ($01 $04 $10 $40: stored, not ORed)
    if y < $30: MISSILE_X[X] = 0; MISSILE_Y[X] = $2F
```
Slots are drawn and moved whether active or not (a free slot has x = 0, off
screen). A slot freed at the top keeps descending from $2F to $2E every frame
and is reset to $2F. The engine keeps the 256-byte missile memory literally,
the renderer draws it.

### 5.5 Missile hits (`VB_HITS`)
For X = 3 down to 0 with `MISSILE_X[X] ≠ 0`: `c = mem[CELL_ADDR(x, y)]`
(§1.4); if `c` is in `HIT_CHARS` (52 entries, index i): the quadrant `i & 3`
(0 top-left, 1 top-right, 2 bottom-left, 3 bottom-right) moves `CELL` to the
object's top-left (`Q1`: −1, `Q2`: −$20, `Q3`: −$21), the handler
`HIT_HANDLERS[i]` runs, then `SND_SHOT = 0`, `SND_SPLASH = 15`, and the
missile is freed (`MISSILE_X[X] = 0`; its y is left, so it keeps being drawn
at x = 0 until it reaches $2F). A character not in the table (empty, shells,
splashes, explosions, the blank tank columns, hard-wall hits are in it) lets
the shot fly on.

`HIT_CHARS` / handlers, with `PUT_EXPLOSION` = frame 0 ($24 $25 / $26 $27) at
`CELL` and `ADD_SCORE(n)` in BCD:
| entries | handler | effect |
|---------|---------|--------|
| $05–$08 soft wall | `HIT_SOFT` | explosion, +15 |
| $09–$0C fuel | `HIT_FUEL` | explosion, +20, `FUEL += 499` (BCD), capped: ≥ 1000 → 999 |
| $0D–$10 ammunition dump | `HIT_AMMO` | explosion, +100 |
| $11–$14 repair | `HIT_REPAIR` | explosion, +30, `JETS += 1` if < 2 |
| $48 $49 $68 $69, $4B $4C $6B $6C, $4E $4F $6E $6F, $51 $52 $71 $72 (tank right, phases 0–3) | `HIT_TANK_R` | explosion over the 2×2 at `CELL`, `mem[CELL+2] = mem[CELL+$22] = 0` (the third column), +55 |
| $55 $56 $75 $76, $58 $59 $78 $79, $5B $5C $7B $7C, $5E $5F $7E $7F (tank left) | `HIT_TANK_L` | explosion at `CELL` (the body's two columns), `mem[CELL−1] = mem[CELL+$1F] = 0` (the column left of it), +55 |
| $01–$04 hard wall | `HIT_HARD` | no explosion: `mem[CELL + $40 + (i & 1)] = $1F` if the hit quadrant was in the bottom row (the splash lands in the row **below** the wall), else `mem[CELL + $20 + (i & 1)] = $1F` (the wall's own bottom character is replaced); `SND_SPLASH = 10` (then 15 by the common tail) |

The 2×2 explosion frame 0 is written wherever `CELL` points after the
quadrant fix — for a tank that is the two body columns, whatever phase.

### 5.6 The jet (`VB_JET_HIT`)
`CELL = CELL_ADDR(JET_X, $B4)`; if any of `mem[CELL]`, `mem[CELL+1]`,
`mem[CELL+$20]`, `mem[CELL+$21]` is ≥ $48 (a tank column, including the
blank $4A/$54 ones) or in `DEADLY` ($01–$08 walls, $15 $17 $19 $1A $1B $1C
shells — not $16 $18 $1D $1E): `DEATH = $FF`. Tested every frame; the main
loop decides what it means (§6.2).

### 5.7 Fuel (`VB_FUEL`)
Every frame with `RTCLOK & $1F == 0` (every 32 frames): `FUEL −= 1` (BCD).
If it went negative (`FUEL_HI` bit 7): `DEATH = $FF`, `FUEL = 099`. Fuel is
therefore worth 32 frames per unit: 099 lasts 3200 frames = 64 s, a fuel tile
adds 499 units.

### 5.8 Status line (`VB_HUD_*`)
`HUD[5..7]` = fuel as three digits (screen codes $10 + digit), `HUD[16..18]` =
the jets: character $6F for each of `JETS + 1` from the right … precisely:
slot k (0..2) shows $6F if `JETS − (2 − k) ≥ 0` else $54; `HUD[26..31]` = the
score, six digits. The line is displayed with the OS character set (§10), so
$6F is the letter `o` and $54 is ATASCII $14, the ball graphic ●: "Damage:ooo"
with three jets, "Damage:o●●" with one — the damage fills up with balls.

### 5.9 End of the VBI
`TRIG_PREV = STRIG0`.

---

## 6. Main loop tail, lives, pause, screens

### 6.1 Start (`INIT`, `RUN`, `GAME_INIT`)
`INIT` (INITAD) finds the DOS loader's IOCB, reads the rest of the file into
`BOARD`, sets `BOARD_END = BOARD + length − 16` (a blank 16-byte row if
nothing was read), rewrites itself into `JMP RUN`, closes the channel and
**falls through into `RUN`** (it never returns to the loader; RUNAD = RUN is
only there for form). `RUN` shows the title screen (§10.2): colours set,
narrow playfield, idle VBI, GTIA/POKEY silenced, OS charset; the text fades
in over 45 frames (COLOR1 luminance 0..14, three frames each); then it waits
for the trigger to be released and then pressed. `GAME_INIT`: PM graphics on
(single-line players, PMBASE $2800, GPRIOR $31 = multicolour players and
missiles as a fifth player), `mem` rows −2..21 and the PM memory zeroed, the
jet shapes copied, the nine colour registers from `COLOURS`, the game display
list and DLIs, the game VBI, charset $24, POKEY on, `GI_VARS` (§1.5),
`LOAD_ROW` for the bottom row, `CH = $FF`, then `MAIN_LOOP`.

### 6.2 After the scan (`ML_FLASH`, `ML_DEATH`)
```
PCOLR0 = 4, PCOLR1 = 8
if FLASH: PCOLR0 = $0A, PCOLR1 = $64, FLASH −= 1
if DEATH:
    DEATH = 0
    if FLASH == 0:                         (a hit while flashing is ignored)
        if JETS == 0: JETS = $FF; FADE_OUT; RUN          (game over → title screen)
        else: JETS −= 1; FLASH = 50; SND_DEATH = 15
```
Losing a jet changes nothing else: the jet stays where it is, the board keeps
scrolling, and for 50 frames it is drawn in the flash colours and cannot be
hit. With `JETS` = 2 at start the player has three jets. Fuel running out
counts as a hit (and refills to 099, §5.7), also while flashing.

### 6.3 Pause (`PAUSE`)
Space (`CH` = $21) in the main loop: `PAUSED = $FF`, then every frame until
`STICK0 ≠ $0F` (any direction); then `PAUSED = 0`, `CH = $FF` and the
**same iteration continues** (scroll and scan run in the unpause frame). While
paused the VBI plays the sound envelopes and nothing else.

### 6.4 ESC (`FADE_OUT`)
`CH` = $1C in the main loop: the idle VBI is installed, POKEY is silenced,
then three tones (AUDF1 $14, AUDF2 $64, AUDF3 $C8) fade with the colours:
for Y = 15, 13, …, 1: `PARITY = Y`, AUDC1–3 = Y, every colour register
$02C0–$02C7 whose luminance is ≥ Y gets luminance Y; three frames per step
(24 frames), then `RUN`: the title screen again. Game over uses the same
sequence. `CH` keeps the ESC code until `GAME_INIT` clears it.

---

## 7. Timing

Frame = 1/50 s (PAL). Everything is counted in frames: sound envelopes, the
32-frame fuel unit, the 50-frame flash, the 45-frame title fade, the 24-frame
fade-out. The one thing not fixed by the code is **how often the main loop
runs** (§2): once per frame when `SCROLL`+`SCAN` fit between two VBIs,
otherwise once per three frames.

The engine counts the CPU cycles of every path it takes through `SCROLL`,
`LOAD_ROW`, `SCAN` and the `VBI` (the 6502 instruction timings of
`game.asm`, checked against py65 in `tests/test_original.py`: the scan within
40 cycles, the VBI within 40) and lets the vertical blank interrupt the scan
when the frame's budget is used up (`Timing`):

```
budget after a VBI = vblank − (that VBI's cycles) + visible − dli_line · (VSCROL + 1)
```

`vblank` = the CPU cycles of the vertical blank left after the OS's own
routines, `visible` = the cycles of the displayed part of the next frame after
ANTIC's DMA, `dli_line` = what one line of `DLI_SCROLL_END`'s `WSYNC` wait
costs. The three constants are **[EST]** in the sense that they come from a
measurement, not from the code: `tools/calibrate_timing.py` runs the same
game in libatari800 (cycle-exact ANTIC/GTIA/POKEY, AltirraOS) and in the
engine and reads where the emulator's scan stands at the end of each frame:
`vblank` = 5883 ± 22 cycles, `visible` = 18645 − 37·(VSCROL+1) with a spread
of about ±25 (sample board without tanks, 830 frames). The scan of an empty
board alone costs 22 222 cycles, which is why **no iteration ever fits in one
frame**: the main loop runs once every three frames (§2), confirmed in
libatari800 on the sample board, an empty board, a wall-only board and a
board full of tanks (`tools/atari800_timing.py`). The constants only decide
at which character the vertical blank interrupts the scan; a different value
moves that point by a few characters.

---

## 8. Engine API
```python
rows = parse_board(text)                                # board.txt / THEJET.PLA -> rows of 16
e = Engine(rows, rnd=lambda: r.randrange(256), rtclok=0, timing=Timing())   # GAME_INIT done
ev = e.tick(Input(stick=0x0F, trig=1, key=None))       # one PAL frame: the VBI, then the main loop
e.mem            # 800 bytes: rows -2..21 then the status line
e.missiles       # 256 bytes of missile memory
e.state          # frame, vscrol, jet_x, missile_x/y, fuel, jets, score, flash, death, row, status, iteration
e.pokey          # AUDF1, AUDC1, ..., AUDF4, AUDC4 as the VBI leaves them
e.scan_cycles, e.scroll_cycles, e.vbi_cycles           # the cycle model's counts
```
`Input.stick` uses the STICK0 bits, `trig` 0/1, `key` an OS key code or None;
`Input.of(up=, left=, right=, fire=, key=)` builds one. The main loop is a
generator inside the engine that yields whenever the original would wait for
the vertical blank or be interrupted by it; `tick` runs the VBI and then
resumes it with the frame's budget (§7). Events (`EventKind`): `VBI` (with
the scan index it interrupted, −1 if idle), `SHOT`, `HIT` (with the object
kind and cell), `SHELL_DROPPED`, `SPLASH`, `JET_HIT`, `FUEL_OUT`, `JET_LOST`,
`GAME_OVER`, `ROW_LOADED`, `SHIFTED`, `PAUSED`, `RESUMED`, `ABORTED`.
`status`: `PLAYING`, `PAUSED`, `GAME_OVER`, `ABORTED` (ESC); the front end
plays the fade-out and the title screen and makes a new engine.

Hard requirements: stdlib only; deterministic given the board, the input
sequence, the timing constants and the generator; the scan implemented
literally as one in-place pass with the pointer semantics of §4;
type-annotated, mypy-clean.

---

## 9. Acceptance tests (`tests/test_engine.py`)

T1 fine scroll and shift: `vscrol` 0→7 with a shift on the first iteration,
then every 8 iterations (4 with the stick up); rows move down; rows 20–21
blank. T2 row loading: tiles, bottom row first, the file order upwards, the
wrap, the EOL correction, a trailing EOL tolerated. T3 the tank rule: `<#`
and `>#` skipped with the stale top half, `< ` placed, a tank in cell 15
skipped when cell 0's bottom-left is set. T4 tank right: phases, one
character per four iterations, blocked → faces left in place; tank left
likewise with the pointer asymmetry; the unmatched-character skip. T5
shells: 1/8 drop from a phase-2 tank's $6E/$7A only, the two cells below
empty; 2 px per iteration, row step, splash; same-pass propagation. T6
explosions: 14 iterations, parity; splashes 5 frames. T7 the jet: x limits,
collision box, `DEADLY`, tanks, death only outside the flash, three jets then
game over, repair adds a jet up to 2. T8 shots: edge-triggered, slot order
3..0, missile memory, freed at $30, the y quirk after freeing. T9 hits: every
handler, quadrant fix, hard-wall splash placement, score BCD, fuel cap. T10
fuel: 32-frame unit, death and refill. T11 pause and ESC. T12 determinism
(hypothesis). Plus `tests/test_original.py`: the engine against the original
running in py65 with the same board, inputs and random numbers, frame by
frame (`mem`, the variables, the missile memory) for several hundred frames
on the article's board and on boards with tanks.

---

## 10. Renderer notes (stage 4)

### 10.1 The game screen (`DL_GAME`)
40 blank scanlines; 20 mode-4 lines with `VSCROL` set, LMS `ROW_0`; the
region is scrolled by `VSCROL_CTR`: row 0 starts at scanline `VSCROL` and the
DLI on row 18 (`DLI_SCROLL_END`) blanks all playfield colours after `VSCROL+1`
scanlines of row 19, so the window is always 153 scanlines: rows 0..19 shifted
up by `VSCROL`, cut after 153 lines. Then `VSCROL+1` blank lines with the
second DLI (`DLI_STATUS`: COLPF2 = 2, COLPF1 = $0E, OS charset) and the
mode-2 status line. Narrow playfield: 256 pixels wide, 16 per cell. Colours
(`COLOURS`): PCOLR0–3 = $04 $08 $06 $0A, COLOR0–4 = $72 $36 $3C $1E $00 —
mode-4 pixel values 1, 2, 3 = COLOR0, COLOR1, COLOR2 (COLOR3 for characters
with bit 7 set: the tank columns $48.., $54.. and the shell/explosion
characters are all < $80, so COLOR3 = $1E is only the fifth-player (missile)
colour). Players: PCOLR0 = 4, PCOLR1 = 8, overlap $0C; flashing: $0A, $64,
overlap $6E. The player/missile vertical position y is scanline y (single-line
resolution, the display list starts at scanline 8): the jet at $B0 = 176 sits
128 scanlines below the top of the window.

### 10.2 The title screen (`DL_TITLE`)
64 blank lines, six mode-2 lines (narrow: 32 characters) from `TITLE_TEXT`:
four lines of the logo in the OS control-graphics characters (screen codes
$49 $4B $4C $4F $55 $59 and inverse), "Written by: Dariusz Zolna 1992",
"(c) 1992 De Jet softteam"; 88 blank lines; the status line. COLOR4 (background)
$10, COLOR2 $10, COLOR1 fading 0..14 in 45 frames. The OS character set is
not part of the repository (`--os-font`); the control-graphics glyphs used by
the logo are quadrant and half blocks and are drawn as such without it.
