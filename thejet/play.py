"""Play The Jet: python -m thejet.play [--board FILE] [--scale N] [--no-sound] [--no-title] [--os-font FILE]

Title screen: the trigger = Ctrl, Z, Return or a joystick button (released, then pressed, as the
original wants). In game: left/right arrows or A/D steer, up arrow or W doubles the scroll speed
(the stick pushed up), the trigger fires, space pauses (any direction resumes), ESC gives up
(the fade-out, then the title screen), Q or the window close quits. --os-font takes a 1 KB Atari
charset dump or an OS ROM image for a pixel-exact status line and title; without it the logo is
drawn from block graphics and the text from a system font.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

import pygame

from .engine import HUD, KEY_ESC, KEY_SPACE, Engine, Input, Status, parse_board
from .render import (FADE_OUT_FRAMES, FPS, TITLE_FADE_FRAMES, JET_COLOURS, JET_FLASH_COLOURS, Renderer, RomData,
                     Sounds, fade_colour, load_os_font, load_rom)

DATA_DIR = Path(__file__).resolve().parent / 'data'
FIRE_KEYS = {pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_z, pygame.K_RETURN, pygame.K_KP_ENTER}
FADE_TONES = (0x14, 0x00, 0x64, 0x00, 0xC8, 0x00, 0x00, 0x00)   # FO_SILENCE: AUDF1-3; AUDC1-3 = Y per step
TITLE_FADE_STEPS, FADE_OUT_STEPS = 15, 8


class Screen(Enum):
    TITLE = 'title'
    PLAY = 'play'
    FADE = 'fade'


class Frontend:
    """The screens of the original outside the engine: RUN (title, fade-in, trigger), the game,
    FADE_OUT after ESC or the third lost jet; one `advance` per PAL frame."""

    def __init__(self, rom: RomData, rows: Sequence[str], renderer: Renderer,
                 rnd: Callable[[], int] | None = None, title: bool = True) -> None:
        self.rom, self.rows, self.renderer = rom, list(rows), renderer
        self.rnd = rnd
        self.engine: Engine | None = None
        self.hud = bytearray(rom.hud_init)              # the title screen shows the last game's status line
        self.mode = Screen.TITLE
        self.frame = 0                                  # RTCLOK stand-in
        self.title_frame = 0                            # frames since RUN
        self.trig_released = False
        self.fade_frame = 0
        self.fade_colours: list[int] = []
        self.regs: list[int] = [0] * 8                  # POKEY registers for this frame
        self.jet_colours = JET_COLOURS
        if not title:
            self.start_game()

    def start_game(self) -> None:
        self.engine = Engine(self.rows, rnd=self.rnd, rtclok=self.frame)
        self.renderer.colours = list(self.rom.colours)  # GI_COLOURS
        self.mode = Screen.PLAY

    def advance(self, inp: Input) -> None:
        self.frame = (self.frame + 1) & 0xFF
        if self.mode is Screen.TITLE:
            self.regs = [0] * 8
            if self.title_frame >= TITLE_FADE_STEPS * TITLE_FADE_FRAMES:   # TI_WAIT_FIRE / TI_WAIT_RELEASE
                if inp.trig:
                    self.trig_released = True
                elif self.trig_released:
                    self.trig_released = False
                    self.start_game()
            self.title_frame += 1
        elif self.mode is Screen.PLAY and self.engine is not None:
            self.engine.tick(inp)
            self.regs = list(self.engine.pokey)
            self.jet_colours = JET_FLASH_COLOURS if self.engine.flash else JET_COLOURS
            self.hud[:] = self.engine.mem[HUD:HUD + 32]
            if self.engine.status in (Status.GAME_OVER, Status.ABORTED):
                self.mode, self.fade_frame = Screen.FADE, 0
                self.fade_colours = list(self.renderer.colours)
        elif self.mode is Screen.FADE:                  # FADE_OUT: one frame, then 8 steps of 3 frames
            step = (self.fade_frame - 1) // FADE_OUT_FRAMES
            if 1 <= self.fade_frame and step < FADE_OUT_STEPS:
                y = 15 - 2 * step
                self.renderer.colours = [fade_colour(c, y) for c in self.fade_colours[:8]] + self.fade_colours[8:]
                self.jet_colours = (fade_colour(self.jet_colours[0], y), fade_colour(self.jet_colours[1], y))
                self.regs = list(FADE_TONES)
                self.regs[1] = self.regs[3] = self.regs[5] = y
            else:
                self.regs = [0] * 8
            self.fade_frame += 1
            if self.fade_frame > 1 + FADE_OUT_STEPS * FADE_OUT_FRAMES:      # JMP RUN
                self.mode, self.title_frame, self.trig_released = Screen.TITLE, 0, False
                self.engine = None

    def draw(self, target: pygame.Surface) -> None:
        if self.mode is Screen.TITLE:
            self.renderer.draw_title(target, self.hud, min(14, self.title_frame // TITLE_FADE_FRAMES))
        elif self.engine is not None:
            e = self.engine
            self.renderer.draw_screen(target, e.mem, e.vscrol, e.jet_x, e.missiles, e.missile_x, self.jet_colours)


def read_input(joystick: pygame.joystick.JoystickType | None, key: int | None) -> Input:
    keys = pygame.key.get_pressed()
    up = keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_KP8]
    left = keys[pygame.K_LEFT] or keys[pygame.K_a] or keys[pygame.K_KP4]
    right = keys[pygame.K_RIGHT] or keys[pygame.K_d] or keys[pygame.K_KP6]
    fire = any(keys[k] for k in FIRE_KEYS)
    if joystick is not None:
        hx, hy = joystick.get_hat(0) if joystick.get_numhats() else (0, 0)
        ax = joystick.get_axis(0) if joystick.get_numaxes() > 1 else 0.0
        ay = joystick.get_axis(1) if joystick.get_numaxes() > 1 else 0.0
        up = up or hy > 0 or ay < -0.5
        left = left or hx < 0 or ax < -0.5
        right = right or hx > 0 or ax > 0.5
        fire = fire or any(joystick.get_button(b) for b in range(joystick.get_numbuttons()))
    return Input.of(up=bool(up), left=bool(left), right=bool(right), fire=bool(fire), key=key)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='The Jet (Atari 8-bit, 1992) - pygame front end')
    ap.add_argument('--board', type=Path, default=DATA_DIR / 'board.txt', help='board text (16 columns per row)')
    ap.add_argument('--scale', type=int, default=3)
    ap.add_argument('--seed', type=int, default=None, help='seed for RANDOM (the shells)')
    ap.add_argument('--no-sound', action='store_true')
    ap.add_argument('--no-title', action='store_true', help='skip the title screen')
    ap.add_argument('--frames', type=int, default=0, help='quit after this many frames (for tests)')
    ap.add_argument('--os-font', type=Path, default=os.environ.get('THEJET_OS_FONT'),
                    help='Atari OS charset (1 KB) or OS ROM image, for the status line and the title')
    ap.add_argument('--data', type=Path, default=DATA_DIR, help='directory with charset.bin, game.bin, text.bin')
    args = ap.parse_args(argv)

    rom = load_rom(args.data)
    rows = parse_board(args.board.read_text(encoding='latin-1'))
    os_font = load_os_font(args.os_font) if args.os_font else None
    rng = random.Random(args.seed)

    pygame.init()
    renderer = Renderer(rom, args.scale, os_font)
    screen = pygame.display.set_mode(renderer.size)
    pygame.display.set_caption('THE JET - Dariusz Zolna 1992')
    sounds = Sounds(enabled=not args.no_sound)
    pygame.joystick.init()
    joystick = pygame.joystick.Joystick(0) if pygame.joystick.get_count() else None
    clock = pygame.time.Clock()
    front = Frontend(rom, rows, renderer, rnd=lambda: rng.randrange(256), title=not args.no_title)

    frames = 0
    while not args.frames or frames < args.frames:
        key: int | None = None
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_q):
                pygame.quit()
                return 0
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                key = KEY_SPACE
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                key = KEY_ESC
        front.advance(read_input(joystick, key))
        front.draw(screen)
        sounds.frame(front.regs)
        pygame.display.flip()
        clock.tick(FPS)
        frames += 1
    pygame.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
