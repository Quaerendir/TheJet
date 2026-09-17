#!/usr/bin/env python3
"""Build the playable Atari file from the extracted data.

Two layouts:

  JET.COM (default)   the article's file: thejet.obj followed by the board (rows joined by
                      ATASCII EOL $9B, none after the last row). The binary's INITAD routine
                      reads the board from the DOS loader's still-open IOCB, so this needs a
                      DOS whose binary loader leaves the file open while it calls INITAD
                      (DOS 2.0/2.5 do). Byte-identical to JET.COM on the archive's disk image.

  --standalone        the same game as a plain DOS binary that any loader or emulator can
                      run: the board is a segment at BOARD ($3F25), BOARD_END ($3F23/$3F24)
                      is filled in, and only RUNAD is set (no INITAD), so INIT's IOCB search
                      never runs. Same memory image at RUN as the original leaves behind.

    python3 tools/build_xex.py [-o JET.COM] [--standalone] [--board board.txt] [--data DIR]
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thejet_extract import BOARD_ADDR, EOL, RUNAD, SEG_TEXT, board_bytes, parse_binary, read_board  # noqa: E402

RUN = 0x3084
BOARD_END = 0x3F23


def segment(start: int, data: bytes) -> bytes:
    return struct.pack('<HH', start, start + len(data) - 1) + data


def build_com(obj: bytes, rows: list[str]) -> bytes:
    return obj + board_bytes(rows)


def build_standalone(obj: bytes, rows: list[str]) -> bytes:
    board = board_bytes(rows)
    out = b'\xff\xff'
    for start, data in parse_binary(obj):
        if start == RUNAD:
            continue                                        # replaced below: RUNAD only
        if start == SEG_TEXT:
            data = data[:-2] + struct.pack('<H', BOARD_ADDR + len(board) - 16)   # what INIT computes
        out += segment(start, data)
    out += segment(BOARD_ADDR, board)
    out += segment(RUNAD, struct.pack('<H', RUN))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description='Build JET.COM or a standalone XEX of The Jet')
    ap.add_argument('-o', '--output', type=Path, default=None)
    ap.add_argument('--data', type=Path, default=ROOT, help='directory with thejet.obj')
    ap.add_argument('--board', type=Path, default=None, help='board text (default: <data>/board.txt)')
    ap.add_argument('--standalone', action='store_true', help='board embedded as a segment, RUNAD only')
    args = ap.parse_args()
    obj = (args.data / 'thejet.obj').read_bytes()
    rows, warn = read_board(args.board or args.data / 'board.txt')
    for w in warn:
        print(f'!! {w}', file=sys.stderr)
    out = args.output or (ROOT / ('thejet.xex' if args.standalone else 'JET.COM'))
    data = build_standalone(obj, rows) if args.standalone else build_com(obj, rows)
    out.write_bytes(data)
    print(f'{out}: {len(data)} bytes, {len(rows)} board rows'
          + (', standalone (RUNAD only)' if args.standalone else ', INITAD reads the board from the DOS channel'))


if __name__ == '__main__':
    main()
