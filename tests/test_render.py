"""Headless tests for the pygame renderer (SDL dummy drivers)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
import pytest  # noqa: E402

from thejet.engine import HUD, Engine, Input, parse_board  # noqa: E402
from thejet.render import (CHAR_PX, HUD_TOP, PF_W, SCREEN_H, TOP_BLANK, WINDOW_LINES, Pokey, Renderer,  # noqa: E402
                           Sounds, TextFont, _lfsr, atari_rgb, fade_colour, load_rom, screen_to_atascii)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def rom():
    return load_rom(ROOT / 'thejet' / 'data')


@pytest.fixture(scope='module', autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def test_rom_data(rom):
    assert len(rom.charset) == 1024
    assert rom.colours == (0x04, 0x08, 0x06, 0x0A, 0x72, 0x36, 0x3C, 0x1E, 0x00)
    assert rom.jet[0] == bytes.fromhex('1010383810 10baba387c545454') and len(rom.jet[1]) == 13
    assert rom.hud_init[:5] == bytes.fromhex('2675656c1a') and len(rom.title_text) == 192
    assert bytes(rom.title_text[128:128 + 8]) == bytes.fromhex('00377269 7474656e')      # " Written"


def test_helpers():
    assert atari_rgb(0) == (0, 0, 0) and atari_rgb(14) == (238, 238, 238)
    assert screen_to_atascii(0x26) == 0x46 and screen_to_atascii(0x49) == 0x09 and screen_to_atascii(0x6F) == 0x6F
    assert fade_colour(0x3C, 9) == 0x39 and fade_colour(0x36, 9) == 0x36 and fade_colour(0x08, 15) == 0x08


def test_lfsr_periods():
    assert len(set(_lfsr(4, 3)[i:i + 4] for i in range(15))) == 15
    p = _lfsr(5, 3)
    assert p[:31] != p[:31][::-1] and len(_lfsr(17, 12)) == 131071


def test_screen_geometry(rom):
    r = Renderer(rom, scale=1)
    assert r.size == (PF_W, SCREEN_H) == (256, 209)
    assert HUD_TOP == 201 and TOP_BLANK + WINDOW_LINES == 193


def test_draw_game_and_title(rom):
    r = Renderer(rom, scale=1)
    e = Engine(parse_board((ROOT / 'board.txt').read_text()))
    e.tick(Input())                                             # the trigger must be seen released first
    e.tick(Input.of(fire=True))
    for _ in range(8):
        e.tick(Input())
    assert e.missile_x[3] != 0
    surf = pygame.Surface(r.size)
    r.draw_game(surf, e, flashing=False)
    # row 0 (the bottom half of the first board row) shows at the window top, scrolled by VSCROL:
    # its scanline `vscrol` is the first visible one; decode that glyph line's pixel values
    col, code = next((c, e.mem[2 * 32 + c]) for c in range(32) if e.mem[2 * 32 + c])
    line = rom.charset[code * 8 + e.vscrol]
    for px in range(4):
        v = (line >> (6 - 2 * px)) & 3
        expect = atari_rgb((0x00, 0x72, 0x36, 0x3C)[v])
        assert surf.get_at((col * CHAR_PX + 2 * px, TOP_BLANK))[:3] == expect, (col, code, px)
    # the jet: player 0's first line is $10 = pixel 3 at x = (jet_x + 3 - 64) * 2, y = $B0 - 8
    assert surf.get_at(((e.jet_x + 3 - 64) * 2, 0xB0 - 8))[:3] == atari_rgb(0x04 | 0x08)   # both players overlap
    # a shot: missile 3 drawn at HPOSM3 + 1 clock, two lines
    y3 = e.missile_y[3]
    assert surf.get_at(((e.missile_x[3] + 1 - 64) * 2, y3 - 8))[:3] == atari_rgb(0x1E)
    assert surf.get_at((0, HUD_TOP + 7))[:3] == atari_rgb(0x02)                 # status line background
    r.draw_title(surf, e.mem[HUD:HUD + 32], 14)
    assert surf.get_at((0, 0))[:3] == atari_rgb(0x10)


def test_text_font_blocks_without_os_font():
    f = TextFont(1)
    g = f.glyph(0x49, (255, 255, 255), (0, 0, 0))                   # control graphics $09: lower-right block
    assert g.get_at((6, 6))[:3] == (255, 255, 255) and g.get_at((1, 1))[:3] == (0, 0, 0)
    g = f.glyph(0xC9, (255, 255, 255), (0, 0, 0))                   # inverse: the other three quadrants
    assert g.get_at((6, 6))[:3] == (0, 0, 0) and g.get_at((1, 1))[:3] == (255, 255, 255)
    g = f.glyph(0x80, (255, 255, 255), (0, 0, 0))                   # inverse space: full block
    assert g.get_at((3, 3))[:3] == (255, 255, 255)


def test_pokey_continuous_tone_and_silence():
    p = Pokey()
    silent = p.render_frame([0] * 8)
    assert len(silent) in (881, 882, 883) and max(silent) == min(silent)
    tone = p.render_frame([0x14, 0xEF, 0, 0, 0, 0, 0, 0])            # channel 1: pure tone, volume 15
    assert max(tone) > min(tone)
    mid = (max(tone) + min(tone)) / 2
    edges = sum(1 for a, b in zip(tone, tone[1:]) if (a > mid) != (b > mid))
    hz = 63337 / (2 * (0x14 + 1))                                   # 64 kHz / (2 * (AUDF + 1))
    assert abs(edges / 2 / (len(tone) / 44100) - hz) < hz * 0.15


def test_sounds_headless():
    s = Sounds(enabled=True)
    s.frame([0x0A, 0x05, 0, 0, 0xB0, 0xE0, 0, 0])
    assert s.last is not None and len(s.last) > 800
