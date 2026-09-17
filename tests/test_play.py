"""The front end's screens (title, game, fade-out) driven headlessly."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
import pytest  # noqa: E402

from thejet.engine import KEY_ESC, Input, parse_board  # noqa: E402
from thejet.play import FADE_OUT_STEPS, Frontend, Screen, main  # noqa: E402
from thejet.render import FADE_OUT_FRAMES, Renderer, load_rom  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module', autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def test_title_fire_play_esc_fade_title():
    rom = load_rom(ROOT / 'thejet' / 'data')
    r = Renderer(rom, 1)
    f = Frontend(rom, parse_board((ROOT / 'board.txt').read_text()), r, rnd=lambda: 0)
    surf = pygame.Surface(r.size)
    for _ in range(44):                                        # TI_FADE_IN: 45 frames, no trigger yet
        f.advance(Input.of(fire=True))
    assert f.mode is Screen.TITLE
    f.advance(Input.of(fire=True))                             # pressed but never seen released: still waiting
    f.advance(Input.of(fire=True))
    assert f.mode is Screen.TITLE
    f.advance(Input())                                         # released ...
    f.advance(Input.of(fire=True))                             # ... then pressed
    assert f.mode is Screen.PLAY and f.engine is not None
    for _ in range(5):
        f.advance(Input.of(right=True))
    f.draw(surf)
    assert f.engine.jet_x == 0x70 + 5
    f.advance(Input(key=KEY_ESC))                              # seen when the next iteration starts
    for _ in range(3):
        if f.mode is Screen.FADE:
            break
        f.advance(Input())
    assert f.mode is Screen.FADE and f.engine is not None
    colours_before = list(r.colours)
    f.advance(Input())                                         # the first fade frame: nothing yet
    f.advance(Input())                                         # step 0: luminances clamped to 15
    f.advance(Input())
    f.advance(Input())
    f.advance(Input())                                         # step 1: clamped to 13
    assert r.colours[4] == 0x72 and r.colours[6] == 0x3C and r.colours[7] == 0x1D and f.regs[1] == 13
    f.draw(surf)
    for _ in range(FADE_OUT_STEPS * FADE_OUT_FRAMES):
        f.advance(Input())
    assert f.mode is Screen.TITLE and f.engine is None and f.regs == [0] * 8
    assert r.colours != colours_before
    f.draw(surf)


def test_main_runs_headless():
    assert main(['--no-title', '--no-sound', '--frames', '30', '--scale', '1']) == 0
    assert main(['--no-sound', '--frames', '10', '--scale', '1']) == 0
