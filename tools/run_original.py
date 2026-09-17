#!/usr/bin/env python3
"""Run the original The Jet code (JET.COM) in py65 with a minimal Atari OS model.

The harness boots the file the way DOS would (segments into memory, INITAD called with
the DOS loader's IOCB still open on the file so that INIT can read the appended board,
then RUNAD), and drives it frame by frame:

  * a VBI every PAL frame: A/X/Y saved, RTCLOK ($14) incremented, the joystick and
    trigger shadows (STICK0 $0278, STRIG0 $0284) and the key code (CH $02FC) set from
    the script, then JMP (VVBLKD) as the OS does; XITVBV ($E462) restores and RTIs;
  * SETVBV ($E45C) stores the deferred vector; CIOV ($E456) serves the two calls INIT
    makes (GET the rest of the file, CLOSE);
  * RANDOM ($D20A) reads come from a seeded generator, so an engine fed the same
    generator sees the same shells dropped;
  * DLIs are not run (they only set colours, CHBASE and the DLI vector).

The game synchronises on RTCLOK; while it spins in one of its wait loops the clock is
advanced straight to the next VBI, so a frame costs only the cycles the game really uses.

    python3 tools/run_original.py [JET.COM] [--frames N] [--seed S] [--dump]
"""
from __future__ import annotations

import argparse
import random
import struct
import sys
from pathlib import Path
from typing import Callable

from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory

ROOT = Path(__file__).resolve().parent.parent

RTCLOK, ATRACT = 0x0014, 0x004D
VDSLST, VVBLKD, SDMCTL, SDLSTL, GPRIOR, STICK0, STRIG0, CHBAS, CH = \
    0x0200, 0x0224, 0x022F, 0x0230, 0x026F, 0x0278, 0x0284, 0x02F4, 0x02FC
COLOURS = 0x02C0
RUNAD, INITAD = 0x02E0, 0x02E2
IOCB, ICHID, ICCOM, ICBAL, ICBAH, ICBLL, ICBLH = 0x0340, 0, 2, 4, 5, 8, 9
CIOV, SETVBV, XITVBV = 0xE456, 0xE45C, 0xE462
RANDOM = 0xD20A
VBI_STUB = 0xE000
PAL_FRAME_CYCLES = 312 * 114
DOS_DL = 0xBC20                    # SDLSTL under DOS 2.5 GRAPHICS 0 on a 48K machine: the board buffer ends here

SCREEN, SCREEN_END = 0x3B43, 0x3E63          # rows -2..21 (24 x 32) then the 32-byte status line
COLS = 32
VARS, VARS_END = 0x3989, 0x39A5
MAIN_LOOP = 0x31A0                            # top of the main loop: LDA $14 / CMP $14 / BEQ
SCAN, SC_CHAR = 0x33B7, 0x33BF
MISSILES = 0x2B00
BOARD_PTR = 0x3F23

# Wait loops: (address of the compare, kind). 'clk' = CMP $14 / BEQ (spin while A == RTCLOK),
# 'clk!' = CMP $14 / BNE (spin while A != RTCLOK), 'trig0' = LDA STRIG0 / BEQ, 'trig1' = ... / BNE.
SPIN_PATTERNS = {b'\xc5\x14\xf0\xfc': 'clk', b'\xc5\x14\xd0\xfc': 'clk!',
                 b'\xad\x84\x02\xf0\xfb': 'trig0', b'\xad\x84\x02\xd0\xfb': 'trig1'}


def parse_com(data: bytes) -> list[tuple[int, bytes, int]]:
    """Segments (start, data, file offset after the segment) up to and including the one that
    sets INITAD. What follows is the appended board, which INIT reads itself; DOS never parses
    it as segments because INIT does not return."""
    segs, p = [], 0
    while p + 4 <= len(data):
        if data[p:p + 2] == b'\xff\xff':
            p += 2
            continue
        start, end = struct.unpack('<HH', data[p:p + 4])
        n = end - start + 1
        if n <= 0 or p + 4 + n > len(data):
            raise ValueError(f'bad segment header at offset {p}')
        segs.append((start, data[p + 4:p + 4 + n], p + 4 + n))
        p += 4 + n
        if start <= INITAD <= end:
            break
    return segs


class Original:
    """The original game running in py65, stepped one PAL frame at a time."""

    def __init__(self, com: bytes, seed: int = 1, cycles_per_frame: int = PAL_FRAME_CYCLES) -> None:
        self.mem = ObservableMemory()
        self.mpu = MPU(memory=self.mem)
        self.rnd = random.Random(seed)
        self.random_reads = 0
        self.cycles_per_frame = cycles_per_frame
        self.frame = 0                              # VBIs fired
        self.main_loops = 0                         # times MAIN_LOOP was reached
        self.loop_frames: list[int] = []            # frame number at each MAIN_LOOP visit
        self.loop_cycles: list[int] = []            # CPU cycles between consecutive MAIN_LOOP visits
        self.stick, self.trig, self.key = 0x0F, 1, None
        self.idle_pc = 0
        self.scan_visits = -1                       # characters SCAN has processed in the current scan
        self.frame_vbi_cycles: list[int] = []       # CPU cycles spent in the VBI, per frame
        self.frame_work_cycles: list[int] = []      # CPU cycles spent outside the VBI and not spinning, per frame
        self._in_vbi: tuple[int, int] | None = None
        self._vbi_work = self._loop_work = 0
        self._last_loop_cycles = 0
        self._file = com
        self._file_pos = 0
        self._spins: dict[int, str] = {}
        self._install_os()
        self._boot(com)

    # ------------------------------------------------------------------ OS model
    def _install_os(self) -> None:
        m = self.mem
        m.subscribe_to_read([RANDOM], self._random)
        # the OS vectors are 3-byte JMPs; the routines live in the stub area
        for addr, code in ((SETVBV, b'\x4c\x00\xe1'), (0xE100, b'\x8c\x24\x02\x8e\x25\x02\x60'),  # STY $224; STX $225; RTS
                           (XITVBV, b'\x4c\x10\xe1'), (0xE110, b'\x68\xa8\x68\xaa\x68\x40'),      # PLA TAY PLA TAX PLA RTI
                           (VBI_STUB, b'\x48\x8a\x48\x98\x48\xe6\x14\x6c\x24\x02'),  # PHA TXA PHA TYA PHA INC $14 JMP ($224)
                           (CIOV, b'\x60')):                                     # trapped before execution
            for i, b in enumerate(code):
                m[addr + i] = b
        m[VVBLKD], m[VVBLKD + 1] = XITVBV & 0xFF, XITVBV >> 8
        m[SDLSTL], m[SDLSTL + 1] = DOS_DL & 0xFF, DOS_DL >> 8
        m[STICK0], m[STRIG0], m[CH] = 0x0F, 1, 0xFF
        for k in range(8):                                                       # IOCB 0..7 closed
            m[IOCB + 16 * k + ICHID] = 0xFF
        m[IOCB + 16 + ICHID] = 0                                                 # IOCB 1: the DOS loader's, open
        m[IOCB + 16 + ICCOM] = 7                                                 # last command: GET

    def _random(self, addr: int) -> int:
        self.random_reads += 1
        return self.rnd.randrange(256)

    def _cio(self) -> None:
        """CIOV trap: X = IOCB offset. GET ($07) hands over the rest of the file, CLOSE ($0C) nothing."""
        m, x = self.mem, self.mpu.x
        cmd = m[IOCB + x + ICCOM]
        if cmd == 7:
            buf = m[IOCB + x + ICBAL] | (m[IOCB + x + ICBAH] << 8)
            want = m[IOCB + x + ICBLL] | (m[IOCB + x + ICBLH] << 8)
            chunk = self._file[self._file_pos:self._file_pos + want]
            for i, b in enumerate(chunk):
                m[buf + i] = b
            self._file_pos += len(chunk)
            m[IOCB + x + ICBLL], m[IOCB + x + ICBLH] = len(chunk) & 0xFF, len(chunk) >> 8
            self.mpu.y = 0x88 if len(chunk) < want else 1                         # EOF / OK
        elif cmd == 0x0C:
            m[IOCB + x + ICHID] = 0xFF
            self.mpu.y = 1
        else:
            raise RuntimeError(f'CIO command ${cmd:02X} not modelled')
        self.mpu.p &= ~self.mpu.NEGATIVE
        self.mpu.pc = self.mpu.stPopWord() + 1                                   # RTS

    def _boot(self, com: bytes) -> None:
        """DOS binary load: segments in order; INITAD called as soon as its segment is in."""
        m = self.mem
        for start, data, after in parse_com(com):
            for i, b in enumerate(data):
                m[start + i] = b
            self._file_pos = after
        for addr in range(0x3000, 0x3B43):
            for pat, kind in SPIN_PATTERNS.items():
                if bytes(m[addr:addr + len(pat)]) == pat:
                    self._spins[addr] = kind
        init = m[INITAD] | (m[INITAD + 1] << 8)
        run = m[RUNAD] | (m[RUNAD + 1] << 8)
        sentinel = 0xFFF0
        self.mpu.sp = 0xFF
        self.mpu.stPushWord(sentinel - 1)
        self.mpu.pc = init
        # INIT never returns: after closing the channel it falls through into RUN ($3084), the
        # loader's return address stays on the stack. RUNAD points at the same place.
        self._run_until(lambda: self.mpu.pc in (sentinel, run), 200_000)
        self.mpu.pc = run
        self._next_vbi = self.mpu.processorCycles + self.cycles_per_frame

    # ------------------------------------------------------------------ stepping
    def _run_until(self, done: Callable[[], bool], limit: int) -> None:
        for _ in range(limit):
            if self.mpu.pc == CIOV:
                self._cio()
            else:
                self.mpu.step()
            if done():
                return
        raise RuntimeError('run_until: limit reached')

    def _spinning(self) -> bool:
        kind = self._spins.get(self.mpu.pc)
        if kind is None:
            return False
        m, a = self.mem, self.mpu.a
        return {'clk': a == m[RTCLOK], 'clk!': a != m[RTCLOK],
                'trig0': m[STRIG0] == 0, 'trig1': m[STRIG0] != 0}[kind]

    def _vbi(self) -> None:
        mpu = self.mpu
        self._in_vbi = (mpu.pc, mpu.sp)
        mpu.stPushWord(mpu.pc)
        mpu.stPush((mpu.p | mpu.UNUSED) & ~mpu.BREAK)
        mpu.p |= mpu.INTERRUPT
        mpu.pc = VBI_STUB
        self.frame += 1

    def step_frame(self, stick: int = 0x0F, trig: int = 1, key: int | None = None,
                   split: int | None = None) -> None:
        """One PAL frame with these inputs: the pending VBI (which reads STICK0/STRIG0/CH as the OS
        stage-2 VBI would have set them) runs first, then the game until the next VBI is due, which
        is left pending. After the call the state is what the frame left behind.

        `split` = a number of SC_CHAR visits: the next VBI fires when SCAN is about to process
        its `split`-th character of the current scan (0-based; a left-facing tank makes the scan
        visit a pointer value twice, so visits are counted, not addresses); or, if the scan does
        not get there this frame, when the game waits. With None the VBI fires after
        `cycles_per_frame` CPU cycles."""
        self.stick, self.trig, self.key = stick, trig, key
        m, mpu = self.mem, self.mpu
        m[STICK0], m[STRIG0] = stick, trig
        if key is not None:
            m[CH] = key
        for _ in range(2_000_000):
            if mpu.pc == CIOV:
                self._cio()
            if self._spinning() or (split is not None and mpu.pc == SC_CHAR and self.scan_visits == split):
                mpu.processorCycles = max(mpu.processorCycles, self._next_vbi)
            if mpu.processorCycles >= self._next_vbi:
                self._next_vbi += self.cycles_per_frame
                self.idle_pc = mpu.pc                       # where the game was when the frame ended
                self.frame_vbi_cycles.append(self._vbi_work)
                self.frame_work_cycles.append(self._loop_work)
                self._vbi_work = self._loop_work = 0
                self._vbi()
                return
            before = mpu.processorCycles
            mpu.step()
            if self._in_vbi is not None:
                self._vbi_work += mpu.processorCycles - before
                if (mpu.pc, mpu.sp) == self._in_vbi:       # RTI brought the game back (no new visit)
                    self._in_vbi = None
                continue
            self._loop_work += mpu.processorCycles - before
            if mpu.pc == SC_CHAR:
                self.scan_visits += 1                           # = characters processed so far
            elif mpu.pc == SCAN:
                self.scan_visits = -1
            if mpu.pc == MAIN_LOOP:
                self.main_loops += 1
                self.loop_frames.append(self.frame)
                self.loop_cycles.append(mpu.processorCycles - self._last_loop_cycles)
                self._last_loop_cycles = mpu.processorCycles
        raise RuntimeError('frame did not end')

    def run_frames(self, n: int, **inp: int) -> None:
        for _ in range(n):
            self.step_frame(**inp)

    def start_game(self, limit: int = 400) -> int:
        """Title screen: fade in (45 frames), then the trigger must be seen released ($30D8) and
        pressed ($30DD). Returns the number of frames used."""
        for f in range(limit):
            self.step_frame(trig=0 if self.idle_pc == 0x30DD else 1)
            if self.main_loops:                 # GAME_INIT done, the first game VBI is pending
                return f + 1
        raise RuntimeError('game did not start')

    # ------------------------------------------------------------------ state
    @property
    def screen(self) -> bytes:
        return bytes(self.mem[SCREEN:SCREEN_END])

    @property
    def vars(self) -> bytes:
        return bytes(self.mem[VARS:VARS_END])

    @property
    def missiles(self) -> bytes:
        return bytes(self.mem[MISSILES:MISSILES + 256])

    @property
    def pokey(self) -> bytes:
        return bytes(self.mem[0xD200:0xD208])

    def rows(self, first: int = -2, last: int = 21) -> list[bytes]:
        return [self.screen[(r + 2) * 32:(r + 3) * 32] for r in range(first, last + 1)]

    def dump(self, first: int = -2, last: int = 21) -> str:
        out = []
        for r, row in zip(range(first, last + 1), self.rows(first, last)):
            out.append(f'{r:3d} ' + ' '.join(f'{b:02X}' for b in row))
        return '\n'.join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description='Run the original The Jet in py65')
    ap.add_argument('com', type=Path, nargs='?', default=ROOT / 'JET.COM')
    ap.add_argument('--frames', type=int, default=300)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--stick', type=lambda s: int(s, 0), default=0x0F)
    ap.add_argument('--fire-every', type=int, default=0, help='press the trigger every N frames')
    ap.add_argument('--dump', action='store_true', help='print the screen memory at the end')
    args = ap.parse_args()

    o = Original(args.com.read_bytes(), seed=args.seed)
    m = o.mem
    board_end = m[BOARD_PTR] | (m[BOARD_PTR + 1] << 8)
    print(f'booted: RUNAD ${m[RUNAD] | m[RUNAD + 1] << 8:04X}, board end pointer ${board_end:04X}, '
          f'INIT patched to {"JMP" if m[0x3000] == 0x4C else "?"} ${m[0x3001] | m[0x3002] << 8:04X}')
    used = o.start_game()
    print(f'title screen: {used} frames until the first main loop')
    for f in range(args.frames):
        trig = 0 if args.fire_every and f % args.fire_every == 0 else 1
        o.step_frame(stick=args.stick, trig=trig)
    print(f'{o.frame} frames, {o.main_loops} main-loop iterations, {o.random_reads} RANDOM reads')
    game = slice(used, used + args.frames)
    vb, wk = o.frame_vbi_cycles[game], o.frame_work_cycles[game]
    tot = [a + b for a, b in zip(vb, wk)]
    print(f'CPU cycles per game frame: VBI max {max(vb)} mean {sum(vb) // len(vb)}; main loop max {max(wk)} '
          f'mean {sum(wk) // len(wk)}; together max {max(tot)} mean {sum(tot) // len(tot)} '
          f'(PAL frame = {PAL_FRAME_CYCLES} before ANTIC DMA)')
    straddled = sum(1 for a, b in zip(o.loop_frames, o.loop_frames[1:]) if b - a != 1)
    print(f'main-loop iterations not one frame apart: {straddled}')
    v = o.vars
    print(f'vars: vscrol {v[1]} toggle {v[2]:02X} flash {v[4]} jet_x ${v[9]:02X} missiles x {list(v[10:14])} '
          f'y {list(v[14:18])} death {v[20]:02X} fuel {v[22]:02X}{v[21]:02X} lives {v[23]} '
          f'score {v[26]:02X}{v[25]:02X}{v[24]:02X}')
    if args.dump:
        print(o.dump())


if __name__ == '__main__':
    main()
