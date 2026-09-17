#!/usr/bin/env python3
"""Render screenshots of the reconstruction headlessly (SDL dummy driver) into docs/.

    python3 tools/screenshots.py [--os-font FILE] [--scale 2]

title.png     the title screen after the fade-in
start.png     the first frames: the bottom of the trench
game*.png     later moments of an autopilot flight on the sample board
tanks.png     a board with tanks, shells and explosions
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from autopilot import autopilot  # noqa: E402
from thejet.engine import HUD, Engine, Input, parse_board  # noqa: E402
from thejet.render import Renderer, load_os_font, load_rom  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--os-font', type=Path, default=os.environ.get('THEJET_OS_FONT'))
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--out', type=Path, default=ROOT / 'docs')
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))
    rom = load_rom(ROOT / 'thejet' / 'data')
    r = Renderer(rom, args.scale, load_os_font(args.os_font) if args.os_font else None)
    surf = pygame.Surface(r.size)

    r.draw_title(surf, rom.hud_init, 14)
    pygame.image.save(surf, str(args.out / 'title.png'))

    rows = parse_board((ROOT / 'board.txt').read_text())
    rng = random.Random(1)
    e = Engine(rows, rnd=lambda: rng.randrange(256))
    shots = {30: 'start.png', 300: 'game1.png', 600: 'game2.png'}
    for f in range(max(shots) + 1):
        e.tick(autopilot(e.mem, e.jet_x, f))
        if f in shots:
            r.draw_game(surf, e, e.flash > 0)
            pygame.image.save(surf, str(args.out / shots[f]))
            print(shots[f], e.state)

    rows = ['#>     <  >    #', '#              #', '#   "" "" ""   #', '#              #'] * 10
    rng = random.Random(2)
    e = Engine(rows, rnd=lambda: rng.randrange(256))
    for f in range(700):
        e.tick(autopilot(e.mem, e.jet_x, f, fire_every=6))
    r.draw_game(surf, e, e.flash > 0)
    pygame.image.save(surf, str(args.out / 'tanks.png'))
    print('tanks.png', e.state, bytes(e.mem[HUD:HUD + 32]))


if __name__ == '__main__':
    main()
