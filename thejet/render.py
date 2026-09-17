"""Stage 4: pygame renderer for The Jet.

Reproduces the original screen (DL_GAME in game.asm): 40 blank scanlines, a 20-row ANTIC
mode-4 narrow playfield (32 characters, 256 pixels) fine-scrolled by VSCROL_CTR and cut by
DLI_SCROLL_END after 153 scanlines, a blank strip, and the mode-2 status line drawn with the
OS character set. The jet is players 0+1 (multicolour), the shots are the missile memory as
the fifth player, below the playfield in priority (GPRIOR $31). The title screen (DL_TITLE)
and the two fades are the same registers the code sets. Sound is a four-channel POKEY model
fed with the register values the engine's VBI writes every frame.
"""
from __future__ import annotations

import array
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pygame

from .engine import COLS, HUD, JET_Y, Engine

CHAR_PX = 8                      # a mode-4 character: 4 colour clocks = 8 hi-res pixels, 8 scanlines
PF_W = COLS * CHAR_PX            # narrow playfield: 256 pixels
PM_LEFT = 64                     # colour clock of the narrow playfield's left edge
PM_TOP = 8                       # player/missile y = frame scanline; the display list starts at scanline 8
TOP_BLANK = 40                   # DL_GAME: 5 x 8 blank scanlines
WINDOW_LINES = 153               # rows 0..19 shifted up by VSCROL, blanked by the DLI after VSCROL+1 lines of row 19
REGION_LINES = 161               # the scroll region including the (VSCROL+1)-line blank instruction after it
HUD_TOP = TOP_BLANK + REGION_LINES
SCREEN_H = HUD_TOP + CHAR_PX     # 209 scanlines
TITLE_TEXT_TOP, TITLE_HUD_TOP = 64, 200        # DL_TITLE: 8 x 8 blank, 6 text lines, 11 x 8 blank, HUD
FPS = 50
TITLE_FADE_FRAMES = 3            # TI_FADE_IN: luminance 0..14, three frames each
FADE_OUT_FRAMES = 3              # FO_STEP: Y = 15, 13, .., 1, three frames each
JET_COLOURS, JET_FLASH_COLOURS = (0x04, 0x08), (0x0A, 0x64)   # PCOLR0/1 in ML_FLASH
HUD_BG, HUD_LUM = 0x02, 0x0E     # DLI_STATUS: COLPF2 = 2, COLPF1 = $0E
TITLE_BG = 0x10                  # RUN: COLOR4 = COLOR2 = $10
BLOCKS = {0x09: (4, 4, 4, 4), 0x0B: (4, 0, 4, 4), 0x0C: (0, 0, 4, 4), 0x0F: (0, 4, 4, 4),
          0x15: (0, 4, 8, 4), 0x19: (0, 0, 4, 8)}          # OS control graphics used by the logo: (x, y, w, h)
BALL = (0x00, 0x3C, 0x7E, 0x7E, 0x7E, 0x7E, 0x3C, 0x00)   # ATASCII $14 (CTRL-T): a lost jet in the status line

BIN_LOAD = 0x3000
COLOURS_ADDR, JET_SHAPE0, JET_SHAPE1, JET_SHAPE_LEN = 0x39A5, 0x39B2, 0x39BF, 13


@dataclass(frozen=True)
class RomData:
    charset: bytes                       # 1024 bytes, 128 glyphs
    colours: tuple[int, ...]             # PCOLR0-3, COLOR0-4 (COLOURS, 9 bytes)
    jet: tuple[bytes, bytes]             # JET_SHAPE0/1, 13 lines each
    title_text: bytes                    # 6 x 32 screen codes (TITLE_TEXT)
    hud_init: bytes                      # the status line as loaded (HUD)


def load_rom(data_dir: Path) -> RomData:
    game = (data_dir / 'game.bin').read_bytes()
    text = (data_dir / 'text.bin').read_bytes()
    charset = (data_dir / 'charset.bin').read_bytes()
    off = COLOURS_ADDR - BIN_LOAD
    return RomData(charset, tuple(game[off:off + 9]),
                   (game[JET_SHAPE0 - BIN_LOAD:JET_SHAPE0 - BIN_LOAD + JET_SHAPE_LEN],
                    game[JET_SHAPE1 - BIN_LOAD:JET_SHAPE1 - BIN_LOAD + JET_SHAPE_LEN]),
                   text[32:32 + 6 * 32], text[:32])


def load_os_font(path: Path) -> bytes:
    """The standard Atari charset: a 1 KB dump, or an OS ROM image (16 KB XL/XE: offset $2000;
    10 KB 400/800 OS-B: offset $800)."""
    data = path.read_bytes()
    if len(data) == 1024:
        return data
    if len(data) == 16384:
        return data[0x2000:0x2400]
    if len(data) == 10240:
        return data[0x800:0xC00]
    raise ValueError(f'{path}: expected a 1 KB charset or a 10/16 KB OS ROM, got {len(data)} bytes')


def atari_rgb(code: int) -> tuple[int, int, int]:
    """GTIA colour code (hue*16 + luminance) -> RGB, a common YIQ approximation."""
    hue, lum = (code >> 4) & 0xF, code & 0xF
    y = lum / 15.0
    if hue == 0:
        v = round(y * 255)
        return v, v, v
    angle = math.radians((hue - 1) * 24.0 - 33.0)
    sat = 0.30
    i, q = sat * math.cos(angle), sat * math.sin(angle)
    r = y + 0.956 * i + 0.621 * q
    g = y - 0.272 * i - 0.647 * q
    b = y - 1.106 * i + 1.703 * q
    return tuple(max(0, min(255, round(v * 255))) for v in (r, g, b))  # type: ignore[return-value]


def screen_to_atascii(code: int) -> int:
    """Screen code (bit 7 stripped) -> ATASCII."""
    c = code & 0x7F
    if c < 0x40:
        return c + 0x20
    if c < 0x60:
        return c - 0x40
    return c


def fade_colour(c: int, y: int) -> int:
    """FO_COLOUR: a colour whose luminance is >= Y is dimmed to luminance Y."""
    return (c & 0xF0) | y if (c & 0x0F) >= y else c


class TextFont:
    """ANTIC mode 2 glyphs (8x8, 32 per narrow line): pixel-exact with the Atari OS charset; without
    it the logo's block-graphics characters are drawn as the quadrant/half blocks they are and
    the text characters come from a system monospace font."""

    def __init__(self, scale: int, os_font: bytes | None = None) -> None:
        self.scale = scale
        self.os_font = os_font
        self._sys: pygame.font.Font | None = None
        if os_font is None:
            pygame.font.init()
            self._sys = pygame.font.SysFont('dejavusansmono,liberationmono,couriernew,monospace', 8 * scale, bold=True)
        self._cache: dict[tuple[int, tuple[int, int, int], tuple[int, int, int]], pygame.Surface] = {}

    def glyph(self, code: int, fg: tuple[int, int, int], bg: tuple[int, int, int]) -> pygame.Surface:
        key = (code, fg, bg)
        surf = self._cache.get(key)
        if surf is not None:
            return surf
        s = self.scale
        inverse, c = code & 0x80, code & 0x7F
        surf = pygame.Surface((CHAR_PX * s, CHAR_PX * s))
        surf.fill(fg if inverse else bg)
        ink = bg if inverse else fg
        atascii = screen_to_atascii(c)
        if self.os_font is not None:
            base = c * 8
            for row in range(8):
                byte = self.os_font[base + row]
                for px in range(8):
                    if byte & (0x80 >> px):
                        surf.fill(ink, (px * s, row * s, s, s))
        elif atascii in BLOCKS:
            x, y, w, h = BLOCKS[atascii]
            surf.fill(ink, (x * s, y * s, w * s, h * s))
        elif atascii == 0x14:
            for row, byte in enumerate(BALL):
                for px in range(8):
                    if byte & (0x80 >> px):
                        surf.fill(ink, (px * s, row * s, s, s))
        elif self._sys is not None and 0x20 < atascii < 0x7F:
            text = self._sys.render(chr(atascii), False, ink, fg if inverse else bg)
            box = pygame.transform.scale(text, (int(CHAR_PX * s * 0.9), int(CHAR_PX * s * 0.95)))
            surf.blit(box, ((CHAR_PX * s - box.get_width()) // 2, (CHAR_PX * s - box.get_height()) // 2))
        self._cache[key] = surf
        return surf

    def draw_line(self, target: pygame.Surface, codes: Sequence[int], top: int, pf1: int, pf2: int) -> None:
        """A mode-2 line: background COLPF2, text in COLPF2's hue with COLPF1's luminance."""
        bg = atari_rgb(pf2)
        fg = atari_rgb((pf2 & 0xF0) | (pf1 & 0x0F))
        s = self.scale
        for k, code in enumerate(codes[:COLS]):
            target.blit(self.glyph(code, fg, bg), (k * CHAR_PX * s, top * s))


class Renderer:
    """Draws the game screen from the engine's state (SPEC.md §10.1)."""
    TRANSPARENT = (1, 2, 3)

    def __init__(self, rom: RomData, scale: int = 3, os_font: bytes | None = None) -> None:
        self.rom = rom
        self.scale = scale
        self.size = (PF_W * scale, SCREEN_H * scale)
        self.font = TextFont(scale, os_font)
        self.colours = list(rom.colours)            # PCOLR0-3, COLOR0-4 (the shadows $02C0-$02C8)
        self._cache: dict[tuple[int, tuple[int, ...]], pygame.Surface] = {}

    # --------------------------------------------------------------- characters
    def char_surface(self, code: int) -> pygame.Surface:
        pf = tuple(self.colours[4:8])
        key = (code, pf)
        surf = self._cache.get(key)
        if surf is not None:
            return surf
        s = self.scale
        surf = pygame.Surface((CHAR_PX * s, CHAR_PX * s))
        surf.fill(self.TRANSPARENT)
        surf.set_colorkey(self.TRANSPARENT)
        palette = (None, atari_rgb(pf[0]), atari_rgb(pf[1]), atari_rgb(pf[3] if code & 0x80 else pf[2]))
        base = (code & 0x7F) * 8
        for row in range(8):
            byte = self.rom.charset[base + row]
            for px in range(4):
                v = (byte >> (6 - 2 * px)) & 3
                if v:
                    surf.fill(palette[v], (px * 2 * s, row * s, 2 * s, s))  # type: ignore[arg-type]
        self._cache[key] = surf
        return surf

    # --------------------------------------------------------------- the game screen
    def draw_game(self, target: pygame.Surface, engine: Engine, flashing: bool) -> None:
        self.draw_screen(target, engine.mem, engine.vscrol, engine.jet_x, engine.missiles, engine.missile_x,
                         JET_FLASH_COLOURS if flashing else JET_COLOURS)

    def draw_screen(self, target: pygame.Surface, mem: bytes | bytearray, vscrol: int, jet_x: int,
                    missiles: bytes | bytearray, missile_x: Sequence[int], jet_colours: tuple[int, int],
                    hud_pf1: int = HUD_LUM, hud_pf2: int = HUD_BG) -> None:
        s = self.scale
        target.fill(atari_rgb(self.colours[8]))                 # COLOR4 everywhere the playfield is blank
        window = pygame.Rect(0, TOP_BLANK * s, PF_W * s, WINDOW_LINES * s)
        target.set_clip(window)
        self.draw_missiles(target, missiles, missile_x)          # fifth player: under the playfield colours
        for row in range(20):
            y = TOP_BLANK - vscrol + row * CHAR_PX
            for col in range(COLS):
                code = mem[(row + 2) * COLS + col]
                if code:
                    target.blit(self.char_surface(code), (col * CHAR_PX * s, y * s))
        target.set_clip(None)
        self.draw_jet(target, jet_x, jet_colours)
        self.font.draw_line(target, mem[HUD:HUD + COLS], HUD_TOP, hud_pf1, hud_pf2)

    def draw_missiles(self, target: pygame.Surface, missiles: bytes | bytearray, missile_x: Sequence[int]) -> None:
        s = self.scale
        colour = atari_rgb(self.colours[7])                     # COLPF3
        for y in range(PM_TOP, PM_TOP + SCREEN_H):
            byte = missiles[y]
            if not byte:
                continue
            for n in range(4):
                pair = (byte >> (2 * n)) & 3
                for bit, dx in ((2, 0), (1, 1)):                  # the high bit is the left colour clock
                    if pair & bit:
                        x = missile_x[n] + dx - PM_LEFT
                        if 0 <= x < PF_W // 2:
                            target.fill(colour, (x * 2 * s, (y - PM_TOP) * s, 2 * s, s))

    def draw_jet(self, target: pygame.Surface, jet_x: int, colours: tuple[int, int]) -> None:
        """Players 0 and 1 at JET_Y with PCOLR0, PCOLR1; overlapping pixels take the OR of both."""
        s = self.scale
        c0, c1, c01 = atari_rgb(colours[0]), atari_rgb(colours[1]), atari_rgb(colours[0] | colours[1])
        for k in range(JET_SHAPE_LEN):
            y = JET_Y + k - PM_TOP
            b0, b1 = self.rom.jet[0][k], self.rom.jet[1][k]
            for px in range(8):
                m = 0x80 >> px
                v = (2 if b1 & m else 0) | (1 if b0 & m else 0)
                if v:
                    x = jet_x + px - PM_LEFT
                    target.fill((c0, c1, c01)[v - 1], (x * 2 * s, y * s, 2 * s, s))

    # --------------------------------------------------------------- the title screen
    def draw_title(self, target: pygame.Surface, hud: bytes | bytearray, lum: int) -> None:
        """DL_TITLE with COLOR4 = COLOR2 = $10 and COLOR1 = the fading luminance (RUN, TI_FADE_IN)."""
        s = self.scale
        target.fill(atari_rgb(TITLE_BG))
        for line in range(6):
            codes = self.rom.title_text[line * COLS:(line + 1) * COLS]
            self.font.draw_line(target, codes, TITLE_TEXT_TOP + line * CHAR_PX, lum, TITLE_BG)
        self.font.draw_line(target, hud[:COLS], TITLE_HUD_TOP, lum, TITLE_BG)
        del s


# ---------------------------------------------------------------- sound (VBI: four POKEY channels)
POKEY_CLOCK = 1_773_447          # PAL POKEY input clock (Hz)
POKEY_BASE_DIV = 28              # AUDCTL = 0: every channel clocked at 64 kHz (1.77 MHz / 28)
SAMPLE_RATE = 44100


def _lfsr(bits: int, tap: int) -> bytes:
    """Output of the maximal-length shift register x^bits + x^tap + 1 (period 2**bits - 1)."""
    reg, out = (1 << bits) - 1, bytearray()
    for _ in range((1 << bits) - 1):
        out.append(reg & 1)
        bit = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (bit << (bits - 1))
    return bytes(out)


class Pokey:
    """Four POKEY channels under AUDCTL = 0 rendered continuously, one PAL frame at a time.

    The polynomial counters run at 1.77 MHz, each channel's divider at 64 kHz and fires every
    AUDF+1 ticks. AUDC: bit 7 = skip the 5-bit poly gate, bit 6 = 4-bit poly instead of the
    17-bit one, bit 5 = pure tone, bits 0-3 = volume. The channel outputs add up.
    """
    POLY4 = _lfsr(4, 3)               # x^4 + x^3 + 1
    POLY5 = _lfsr(5, 3)               # x^5 + x^3 + 1
    POLY17: bytes | None = None

    def __init__(self, sample_rate: int = SAMPLE_RATE, amplitude: int = 9000) -> None:
        self.sample_rate = sample_rate
        self.amplitude = amplitude
        if Pokey.POLY17 is None:
            Pokey.POLY17 = _lfsr(17, 12)          # x^17 + x^12 + 1
        self.counter = [0, 0, 0, 0]
        self.out = [0, 0, 0, 0]
        self.clock = 0                            # 1.77 MHz cycles, for the polynomial counters
        self.residual = 0.0                       # fractional 64 kHz ticks carried between frames
        self.pending = 0.0                        # fractional output samples carried between frames

    def render_frame(self, regs: Sequence[int], seconds: float = 1 / FPS) -> array.array[int]:
        base_hz = POKEY_CLOCK / POKEY_BASE_DIV
        n_base_f = base_hz * seconds + self.residual
        n_base = int(n_base_f)
        self.residual = n_base_f - n_base
        p4, p5, p17 = Pokey.POLY4, Pokey.POLY5, Pokey.POLY17 or b''
        levels = array.array('H', bytes(2 * n_base))
        for t in range(n_base):
            self.clock += POKEY_BASE_DIV
            total = 0
            for ch in range(4):
                audf, audc = regs[2 * ch], regs[2 * ch + 1]
                if self.counter[ch] == 0:
                    self.counter[ch] = audf
                    if audc & 0x80 or p5[self.clock % 31]:
                        if audc & 0x20:
                            self.out[ch] ^= 1
                        elif audc & 0x40:
                            self.out[ch] = p4[self.clock % 15]
                        else:
                            self.out[ch] = p17[self.clock % 131071]
                else:
                    self.counter[ch] -= 1
                if self.out[ch]:
                    total += audc & 0x0F
            levels[t] = total
        n_out_f = self.sample_rate * seconds + self.pending
        n_out = int(n_out_f)
        self.pending = n_out_f - n_out
        samples = array.array('h')
        gain = self.amplitude / 15
        for k in range(n_out):
            a = k * n_base // n_out
            b = max(a + 1, (k + 1) * n_base // n_out)
            mean = sum(levels[a:b]) / (b - a)
            samples.append(int(mean * gain) - self.amplitude)
        return samples


class Sounds:
    """Feeds the POKEY model with the engine's registers every frame and streams the result."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = False
        self._pokey = Pokey()
        self._channel: pygame.mixer.Channel | None = None
        self.last: array.array[int] | None = None
        if not enabled:
            return
        try:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
            self._channel = pygame.mixer.Channel(0)
        except pygame.error:
            return
        self.enabled = True

    def frame(self, regs: Sequence[int]) -> None:
        self.last = self._pokey.render_frame(regs)
        if not self.enabled or self._channel is None:
            return
        snd = pygame.mixer.Sound(buffer=self.last.tobytes())
        if self._channel.get_busy():
            self._channel.queue(snd)
        else:
            self._channel.play(snd)
