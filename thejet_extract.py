#!/usr/bin/env python3
"""
thejet_extract.py -- Stage 1 of The Jet (Atari 8-bit, Dariusz Zolna 1992,
Tajemnice ATARI 6-7/92) conversion pipeline.

The listing is a hex listing for the magazine's "Zgrywus" utility: 320 DATA
lines of hexadecimal digits (13 bytes per line, 10 on the last) that Zgrywus
writes verbatim to a file, JET.OBJ. That file is an Atari DOS binary load
file (segments with $FFFF markers, RUNAD/INITAD at $02E0). The board is a
plain text file (16 characters per row, ATASCII EOL $9B between rows, none
after the last) that the player appends to JET.OBJ; the game's INITAD routine
reads it from the still-open DOS loader channel.

Writes:
  thejet.obj   -- the bytes of the DATA lines: what Zgrywus produced (identical
                  to THEJET.COM on the archive's disk image)
  charset.bin  -- segment $2400-$27FF: the redefined character set (128 glyphs)
  game.bin     -- segment $3000-$3B42: 6502 code, tables, display lists
  text.bin     -- segment $3E43-$3F24: status line, title screen, board pointer
  board.txt    -- the board, 142 rows of 16, with a legend
  meta.json    -- segments, memory map, colours, tables
  JET.COM      -- with --com: thejet.obj + board, the playable file (step 3 of
                  the article, "Append"), identical to the archive's JET.COM

Author: Quaerendir
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

EOL = 0x9B
BOARD_W = 16
BOARD_CHARS = set(' #"!$%<>')        # the loader's table at $39CB; anything else is empty
RUNAD, INITAD = 0x02E0, 0x02E2
SEG_CHARSET, SEG_GAME, SEG_TEXT = 0x2400, 0x3000, 0x3E43
BOARD_ADDR = 0x3F25                  # INIT reads the board here (LDA #$25 / #$3F into ICBAL/H)
HEXLINE = re.compile(r'^[0-9a-fA-F]+$')


def data_lines(text: str) -> list[tuple[int, str]]:
    """(line number, payload) of every DATA line of the listing, in listing order."""
    out = []
    for phys in text.replace('\r\n', '\n').replace('\x9b', '\n').split('\n'):
        m = re.match(r'^(\d+) DATA (.*)$', phys.rstrip())
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def decode_listing(text: str) -> tuple[bytes, list[str]]:
    """Zgrywus: every DATA line is hex digits, written as bytes in order. No checksum."""
    warn = []
    blob = bytearray()
    for no, payload in data_lines(text):
        if not HEXLINE.match(payload) or len(payload) % 2:
            warn.append(f'line {no}: not an even number of hex digits: {payload!r}')
            continue
        blob += bytes.fromhex(payload)
    return bytes(blob), warn


def parse_binary(blob: bytes) -> list[tuple[int, bytes]]:
    """Atari DOS binary load file -> [(start, data)]; $FFFF markers may precede any segment."""
    segs = []
    p = 0
    while p < len(blob):
        if blob[p:p + 2] == b'\xff\xff':
            p += 2
            continue
        if p + 4 > len(blob):
            raise ValueError(f'truncated segment header at offset {p}')
        start, end = struct.unpack('<HH', blob[p:p + 4])
        p += 4
        n = end - start + 1
        if n <= 0 or p + n > len(blob):
            raise ValueError(f'bad segment ${start:04X}-${end:04X} at offset {p - 4}')
        segs.append((start, blob[p:p + n]))
        p += n
    return segs


def read_board(path: Path) -> tuple[list[str], list[str]]:
    """Board text: LF or CR/LF or ATASCII $9B row separators. Returns rows and warnings."""
    raw = path.read_bytes().replace(b'\r\n', b'\n').replace(bytes([EOL]), b'\n')
    if raw.endswith(b'\n'):
        raw = raw[:-1]
    rows = [r.decode('latin-1') for r in raw.split(b'\n') if not r.startswith(b';')]   # board.txt legend
    warn = []
    for k, r in enumerate(rows):
        if len(r) != BOARD_W:
            warn.append(f'row {k + 1}: {len(r)} characters, the game assumes {BOARD_W} (the board shifts)')
        odd = sorted(set(r) - BOARD_CHARS)
        if odd:
            warn.append(f'row {k + 1}: characters {odd} are empty space to the game')
    for k, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in '<>' and x + 1 < len(r) and r[x + 1] != ' ':
                warn.append(f'row {k + 1}: tank at column {x} touches {r[x + 1]!r} on its right '
                            f'(the article warns against it; the loader skips such a tank)')
    return rows, warn


def board_bytes(rows: list[str]) -> bytes:
    """THEJET.PLA layout: rows separated by $9B, no EOL after the last (the article's step 2)."""
    return bytes([EOL]).join(r.encode('latin-1') for r in rows)


def glyph_art(charset: bytes, first: int = 0, count: int = 128) -> str:
    lines = []
    for g in range(first, min(first + count, len(charset) // 8)):
        rows = charset[g * 8:g * 8 + 8]
        lines.append(f'--- glyph ${g:02X} ({g}) ---')
        lines.extend(''.join('#' if b & (0x80 >> i) else '.' for i in range(8)) for b in rows)
    return '\n'.join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description='Extract data from the The Jet hex listing')
    ap.add_argument('listing', type=Path, nargs='?', default=Path('TheJet.bas'))
    ap.add_argument('board', type=Path, nargs='?', default=Path('plansze.txt'))
    ap.add_argument('-o', '--outdir', type=Path, default=Path('.'))
    ap.add_argument('--com', type=Path, metavar='FILE', help='also write the merged playable file (JET.COM)')
    ap.add_argument('--glyphs', action='store_true', help='print the 128 glyphs as ASCII art')
    args = ap.parse_args()

    blob, warn = decode_listing(args.listing.read_text(encoding='latin-1'))
    segs = parse_binary(blob)
    by_start = dict(segs)
    for start in (SEG_CHARSET, SEG_GAME, SEG_TEXT, RUNAD):
        if start not in by_start:
            sys.exit(f'segment ${start:04X} missing from the binary (got {[hex(s) for s, _ in segs]})')
    vec = by_start[RUNAD]
    runad, initad = struct.unpack('<HH', vec[:4])
    if len(by_start[SEG_CHARSET]) != 1024:
        warn.append(f'charset segment is {len(by_start[SEG_CHARSET])} bytes, expected 1024')
    text = by_start[SEG_TEXT]
    board_end = struct.unpack('<H', text[-2:])[0]      # $3F23/$3F24: INIT overwrites it with the board end
    rows, board_warn = read_board(args.board)
    warn += board_warn
    for w in warn:
        print(f'!! {w}', file=sys.stderr)

    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / 'thejet.obj').write_bytes(blob)
    (args.outdir / 'charset.bin').write_bytes(by_start[SEG_CHARSET])
    (args.outdir / 'game.bin').write_bytes(by_start[SEG_GAME])
    (args.outdir / 'text.bin').write_bytes(text)
    with open(args.outdir / 'board.txt', 'w') as f:
        f.write('; The Jet (C) 1992 Dariusz Zolna / Tajemnice ATARI 6-7/92 -- the board printed with the article\n')
        f.write('; legend: # hard wall  " soft wall  ! repair  $ ammunition dump (bonus)  % fuel  < tank facing left\n')
        f.write('; > tank facing right  (space or anything else) empty.  16 columns; the game starts at the LAST row\n')
        f.write('; and scrolls upwards through the file, then wraps around to the last row again.\n')
        f.write(f'; rows: {len(rows)}\n')
        for r in rows:
            f.write(r + '\n')
    meta = {
        'source': {
            'listing': args.listing.name,
            'board': args.board.name,
            'article': '6-7_92_thejet.html',
            'archive': 'https://tajemnice.atari8.info/6-7_92/6-7_92_listingi.zip -> 6-7_92.atr -> '
                       'THEJET.LST, THEJET.COM, THEJET.PLA, JET.COM',
        },
        'obj': {'size': len(blob), 'segments': [{'start': f'${s:04X}', 'end': f'${s + len(d) - 1:04X}',
                                                 'size': len(d)} for s, d in segs],
                'runad': f'${runad:04X}', 'initad': f'${initad:04X}'},
        'memory': {
            'charset': '$2400', 'chbas': 0x24,
            'code': '$3000', 'init': '$3000', 'run': '$3084',
            'pm_base': '$2800', 'missiles': '$2B00', 'player0': '$2C00', 'player1': '$2D00',
            'jet_shape_y': 0xB0, 'jet_shapes': ['$39B2', '$39BF'], 'jet_shape_len': 13,
            'colours_02C0_02C8': '$39A5',
            'display_list_game': '$3B00', 'display_list_title': '$3B22',
            'screen': '$3B43', 'screen_rows': 24, 'screen_cols': 32, 'screen_lms': '$3B83',
            'hud': '$3E43', 'title_text': '$3E63', 'board_end_ptr': '$3F23', 'board': f'${BOARD_ADDR:04X}',
            'board_end_ptr_in_listing': f'${board_end:04X}',
            'variables': '$3989-$39A4',
        },
        'board': {'width': BOARD_W, 'rows': len(rows), 'bytes': len(board_bytes(rows)),
                  'chars': sorted(set(''.join(rows)))},
    }
    (args.outdir / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
    if args.com:
        args.com.write_bytes(blob + board_bytes(rows))

    print(f'OK: thejet.obj {len(blob)} B, {len(segs)} segments '
          + ', '.join(f'${s:04X}-${s + len(d) - 1:04X}' for s, d in segs)
          + f', RUNAD ${runad:04X} INITAD ${initad:04X}; board {len(rows)} rows'
          + (f'; {args.com} {len(blob) + len(board_bytes(rows))} B' if args.com else '')
          + (f'; {len(warn)} warnings' if warn else ''))
    if args.glyphs:
        print(glyph_art(by_start[SEG_CHARSET]))


if __name__ == '__main__':
    main()
