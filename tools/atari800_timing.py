#!/usr/bin/env python3
"""Measure the main-loop cadence of the original in a cycle-exact emulator (libatari800).

py65 (`tools/run_original.py`) counts CPU cycles but knows nothing of ANTIC's DMA, the DLIs'
WSYNC waits or the OS vertical blank. This runs `thejet.xex` (the standalone build, any loader
can run it) in libatari800 with the built-in AltirraOS and counts, frame by frame, how often
the main loop ran: VSCROL_CTR ($398A) changes on every iteration.

    python3 tools/atari800_timing.py path/to/libatari800.so [thejet.xex] [--frames N]

Build the library from the atari800 5.2.0 sources: configure --target=libatari800 CFLAGS=-fPIC,
make, then link the (content-unique) objects of src/libatari800.a into a shared library.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RTCLOK, STICK0, STRIG0 = 0x14, 0x278, 0x284
VSCROL_CTR, JET_X, JETS, FUEL, PARITY = 0x398A, 0x3992, 0x39A0, 0x399E, 0x398C
MAIN_LOOP_PC = 0x31A0


class Input(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ubyte) for n in (
        'keychar', 'keycode', 'special', 'shift', 'control', 'start', 'select', 'option',
        'joy0', 'trig0', 'joy1', 'trig1', 'joy2', 'trig2', 'joy3', 'trig3',
        'mousex', 'mousey', 'mouse_buttons', 'mouse_mode')]


class Atari:
    def __init__(self, lib: Path, xex: Path, pal: bool = True) -> None:
        self.lib = ctypes.CDLL(str(lib))
        self.lib.libatari800_get_main_memory_ptr.restype = ctypes.POINTER(ctypes.c_ubyte * 65536)
        self.lib.libatari800_error_message.restype = ctypes.c_char_p
        args = [b'atari800', b'-xl', b'-xl-rev', b'altirra', b'-nobasic', b'-pal' if pal else b'-ntsc',
                str(xex).encode()]
        argv = (ctypes.c_char_p * len(args))(*args)
        if not self.lib.libatari800_init(len(args), argv):
            raise RuntimeError(self.lib.libatari800_error_message().decode())
        self.mem = self.lib.libatari800_get_main_memory_ptr().contents
        self.inp = Input()
        self.lib.libatari800_clear_input_array(ctypes.byref(self.inp))
        self.frame = 0

    def step(self, stick: int = 0x0F, trig: int = 1) -> None:
        self.inp.joy0 = (~stick) & 0x0F               # libatari800: bits = directions pressed
        self.inp.trig0 = 0 if trig else 1            # libatari800: 1 = pressed
        self.lib.libatari800_next_frame(ctypes.byref(self.inp))
        self.frame += 1

    def __getitem__(self, addr: int) -> int:
        return self.mem[addr]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('lib', type=Path)
    ap.add_argument('xex', type=Path, nargs='?', default=ROOT / 'thejet.xex')
    ap.add_argument('--frames', type=int, default=600)
    ap.add_argument('--boot', type=int, default=400, help='frames to let the OS boot and load the file')
    args = ap.parse_args()
    a = Atari(args.lib, args.xex)
    for _ in range(args.boot):
        a.step()
        if a[JET_X] == 0x70 and a[JETS] == 2:
            break
    print(f'after {a.frame} frames: RTCLOK {a[RTCLOK]}, STICK0 ${a[STICK0]:02X}, STRIG0 {a[STRIG0]}, '
          f'JET_X ${a[JET_X]:02X}, JETS {a[JETS]}')
    # the title screen: trigger released, then pressed, then released again
    for _ in range(60):
        a.step(trig=1)
    for _ in range(3):
        a.step(trig=0)
    a.step(trig=1)
    print(f'frame {a.frame}: JET_X ${a[JET_X]:02X} JETS {a[JETS]} FUEL {a[FUEL]:02X} vscrol {a[VSCROL_CTR]}')
    last = a[VSCROL_CTR]
    iters, gaps, since = 0, [], 0
    hist: dict[int, int] = {}
    splits: list[int] = []                      # SCAN_PTR at the frame end while the scan is in progress
    for f in range(args.frames):
        a.step(stick=0x07 if f < 7 else 0x0F, trig=1)
        v = a[VSCROL_CTR]
        since += 1
        if v != last:
            iters += 1
            hist[since] = hist.get(since, 0) + 1
            gaps.append(since)
            since = 0
            last = v
        ptr = a[0xB0] | (a[0xB1] << 8)
        if 0x3B63 <= ptr < 0x3E03:
            splits.append(ptr - 0x3B63)
        if a[JETS] == 0xFF:
            print('game over at frame', f)
            break
    print(f'{f + 1} frames, {iters} main-loop iterations; frames per iteration histogram: {dict(sorted(hist.items()))}')
    print('first 80 gaps:', gaps[:80])
    if splits:
        print(f'scan index at the frame end when a scan was in progress ({len(splits)} frames): '
              f'min {min(splits)} max {max(splits)} mean {sum(splits) // len(splits)}; first 40: {splits[:40]}')
    print(f'JET_X ${a[JET_X]:02X} JETS {a[JETS]} FUEL {a[FUEL]:02X} STICK0 ${a[STICK0]:02X}')


if __name__ == '__main__':
    main()
