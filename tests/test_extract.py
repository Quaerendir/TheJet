"""Stage 1: the listing, the archive's files and the extractor's outputs agree byte for byte."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import thejet_extract as ex  # noqa: E402
from build_xex import build_com, build_standalone  # noqa: E402

LST = (ROOT / 'THEJET.LST').read_bytes()
COM = (ROOT / 'THEJET.COM').read_bytes()
PLA = (ROOT / 'THEJET.PLA').read_bytes()
BAS = (ROOT / 'TheJet.bas').read_text(encoding='latin-1')

# SHA-256 of the files taken from 6-7_92.atr (6-7_92_listingi.zip of the archive, 2026-09-17)
ARCHIVE = {'THEJET.LST': 'a9c0e45defc3bf3df74be9af960921e058862e1864261512671f2e8ebc1e0554',
           'THEJET.COM': 'f5604694edb33d7b1b89c758050a598092de7b06779be5ce1525ca3a186aa1e5',
           'THEJET.PLA': '27ff3882bd92a77a70d96d6ca2f4e1a93e274280eb661b7d16a032353a8461c3',
           'JET.COM': 'fc4d48a21609d7e16a3ce5280a3fda30d91f436c1436cc8e30eee243842448ee'}


def test_archive_files_unchanged():
    for name, digest in ARCHIVE.items():
        if name != 'JET.COM':
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def test_listing_text_equals_the_archive_lst():
    lst_lines = [ln for ln in LST.decode('latin-1').split('\x9b') if ln]
    bas_lines = [ln for ln in BAS.replace('\r\n', '\n').split('\n') if ln]
    assert len(lst_lines) == len(bas_lines) == 325
    assert [ln.rstrip() for ln in lst_lines] == [ln.rstrip() for ln in bas_lines]


def test_listing_decodes_to_thejet_com():
    blob, warn = ex.decode_listing(BAS)
    assert warn == [] and blob == COM and len(blob) == 4157
    segs = ex.parse_binary(blob)
    assert [(s, len(d)) for s, d in segs] == [(0x2400, 1024), (0x3000, 2883), (0x3E43, 226), (0x02E0, 4)]
    assert dict(segs)[0x02E0] == b'\x84\x30\x00\x30'            # RUNAD $3084, INITAD $3000


def test_board_text_equals_the_archive_pla_and_jet_com():
    rows, warn = ex.read_board(ROOT / 'plansze.txt')
    assert len(rows) == 142 and all(len(r) == 16 for r in rows)
    assert ex.board_bytes(rows) + b'\x9b' == PLA
    assert hashlib.sha256(build_com(COM, rows)).hexdigest() == ARCHIVE['JET.COM']
    assert build_com(COM, rows) == COM + PLA[:-1]                 # the article's Append, no EOL after the last row
    assert sum(1 for w in warn if 'tank' in w) == 30              # every '<' has a '#' on its right
    assert ex.read_board(ROOT / 'board.txt')[0] == rows           # the extractor's copy, legend skipped


def test_extractor_outputs_are_committed():
    blob, _ = ex.decode_listing(BAS)
    segs = dict(ex.parse_binary(blob))
    assert (ROOT / 'thejet.obj').read_bytes() == blob
    assert (ROOT / 'charset.bin').read_bytes() == segs[0x2400]
    assert (ROOT / 'game.bin').read_bytes() == segs[0x3000]
    assert (ROOT / 'text.bin').read_bytes() == segs[0x3E43]
    for name in ('charset.bin', 'game.bin', 'text.bin', 'board.txt', 'meta.json'):
        assert (ROOT / 'thejet' / 'data' / name).read_bytes() == (ROOT / name).read_bytes(), name


def test_standalone_xex_layout():
    rows, _ = ex.read_board(ROOT / 'plansze.txt')
    xex = build_standalone(COM, rows)
    segs = ex.parse_binary(xex)
    assert [s for s, _ in segs] == [0x2400, 0x3000, 0x3E43, 0x3F25, 0x02E0]
    d = dict(segs)
    assert d[0x02E0] == b'\x84\x30' and d[0x3F25] == PLA[:-1]
    end = 0x3F25 + len(PLA) - 1 - 16
    assert d[0x3E43][-2:] == bytes((end & 0xFF, end >> 8))         # BOARD_END as INIT computes it


def test_game_asm_is_current():
    asm = (ROOT / 'game.asm').read_text()
    assert asm.count('\n') > 1000 and 'H_TANK_DROP' in asm and 'VB_UNREACHED' in asm
    for line in asm.splitlines():
        m = re.match(r'^([0-9A-F]{4})  ((?:[0-9A-F]{2} ?)+)\s{2,}', line)
        if m and 0x3000 <= int(m.group(1), 16) < 0x3B43:
            addr, raw = int(m.group(1), 16), bytes.fromhex(m.group(2).replace(' ', ''))
            assert (ROOT / 'game.bin').read_bytes()[addr - 0x3000:addr - 0x3000 + len(raw)] == raw, line
