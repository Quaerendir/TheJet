#!/usr/bin/env python3
"""Annotated recursive-descent 6502 disassembly of The Jet (thejet.obj) with py65.

    pip install py65
    python3 thejet_disasm.py thejet.obj > game.asm

Entry points: INITAD ($3000), RUNAD ($3084), the two deferred VBI routines, the DLIs and every
routine reached through the three jump tables (SCAN_HANDLERS, HIT_HANDLERS, QUADRANT_TAB), which
control-flow analysis cannot see through. Unreached bytes are printed as data.
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler

NAMES = {
    0x3000: 'INIT', 0x3002: 'IN_FIND_IOCB', 0x3015: 'IN_NO_IOCB', 0x3017: 'IN_READ', 0x3035: 'IN_END_PTR',
    0x3063: 'IN_BLANK_ROW', 0x306D: 'IN_PATCH',
    0x3084: 'RUN', 0x3091: 'RU_WAIT', 0x30C5: 'TI_FADE_IN', 0x30C7: 'TI_STEP', 0x30CF: 'TI_WAIT3',
    0x30D8: 'TI_WAIT_FIRE', 0x30DD: 'TI_WAIT_RELEASE',
    0x30E2: 'GAME_INIT', 0x30FB: 'GI_CLEAR', 0x30FE: 'GI_CLEAR_LOOP', 0x3119: 'GI_SHAPES', 0x311B: 'GI_SHAPES_LOOP',
    0x312A: 'GI_COLOURS', 0x312C: 'GI_COLOURS_LOOP', 0x3166: 'GI_VARS', 0x316A: 'GI_VARS_LOOP', 0x3177: 'GI_MISSILES',
    0x31A0: 'MAIN_LOOP', 0x31A2: 'ML_WAIT', 0x31B0: 'ML_SPACE', 0x31B7: 'ML_FRAME', 0x31CE: 'ML_WAIT_SCAN',
    0x31D2: 'ML_FLASH', 0x31E6: 'ML_DEATH', 0x31EB: 'ML_DIE', 0x31F5: 'ML_LIVES', 0x31FA: 'ML_LOSE_JET',
    0x320A: 'GAME_OVER', 0x320D: 'FADE_OUT', 0x320F: 'FO_WAIT', 0x3220: 'FO_SILENCE', 0x3237: 'FO_STEP',
    0x3245: 'FO_COLOUR', 0x325A: 'FO_NEXT', 0x3262: 'FO_WAIT3',
    0x326D: 'PAUSE', 0x3274: 'PA_WAIT',
    0x3288: 'SCROLL', 0x32A0: 'SC_SHIFT', 0x32AA: 'SC_COPY', 0x332E: 'SC_CLEAR_BOTTOM', 0x3332: 'SC_CLEAR_LOOP',
    0x3338: 'SC_TOGGLE', 0x3342: 'RTS1',
    0x3343: 'LOAD_ROW', 0x3358: 'LR_START', 0x335C: 'LR_CELL', 0x3362: 'LR_MATCH', 0x336A: 'LR_TILE',
    0x3376: 'LR_PUT', 0x338E: 'LR_NEXT', 0x3395: 'LR_PREV_ROW', 0x33AC: 'LR_WRAP', 0x33B6: 'RTS2',
    0x33B7: 'SCAN', 0x33BF: 'SC_CHAR', 0x33C9: 'SC_MATCH', 0x33D1: 'SC_DISPATCH', 0x33E0: 'SC_JSR',
    0x33E3: 'SC_NEXT', 0x33E9: 'SC_END_TEST', 0x33F3: 'SC_END',
    0x33FC: 'H_TANK_R', 0x340A: 'TR_STEP', 0x3416: 'TR_ADVANCE', 0x342E: 'TR_TURN',
    0x3435: 'H_TANK_L', 0x3443: 'TL_STEP', 0x345C: 'TL_ADVANCE', 0x346D: 'TL_TURN',
    0x347B: 'H_TANK_DROP', 0x3483: 'TD_CHECK', 0x348E: 'TD_DROP',
    0x34A3: 'H_SHELL', 0x34B8: 'SH_ROW_END', 0x34BE: 'SH_MOVE', 0x34D1: 'SH_SPLASH',
    0x34E2: 'H_SPLASH', 0x34F2: 'H_EXPLOSION', 0x34FA: 'EX_FIND', 0x3500: 'EX_FIND_LOOP', 0x350D: 'EX_CLEAR',
    0x351E: 'EX_NEXT', 0x3536: 'EX_DONE', 0x3539: 'NEXT_CHAR',
    0x3540: 'DRAW_TANK', 0x354D: 'PUT3', 0x354F: 'PUT3_LOOP',
    0x3559: 'DLI_SCROLL_END', 0x3561: 'DS_WSYNC', 0x3584: 'DLI_STATUS', 0x35AA: 'DLI_STATUS2',
    0x35C3: 'VBI', 0x35CD: 'VB_SND_SHELL', 0x35EF: 'VB_SND_SPLASH', 0x361B: 'VB_SND_SHOT', 0x363B: 'VB_SND_DEATH',
    0x365D: 'VB_PAUSED', 0x3665: 'VB_STICK', 0x3676: 'VB_LEFT', 0x3687: 'VB_FIRE', 0x3691: 'VB_SLOT', 0x3693: 'VB_SLOT_LOOP',
    0x369E: 'VB_SHOOT', 0x36CC: 'VB_UNREACHED', 0x36DA: 'VB_JET', 0x36E3: 'VB_MISSILES_CLEAR', 0x36E7: 'VB_MC_LOOP',
    0x36ED: 'VB_MISSILES', 0x36EF: 'VB_MISSILE', 0x3713: 'VB_MISSILE_NEXT',
    0x3716: 'VB_HITS', 0x3718: 'VH_MISSILE', 0x3735: 'VH_FIND', 0x3737: 'VH_FIND_LOOP', 0x3742: 'VH_DISPATCH',
    0x3762: 'VH_JSR_QUADRANT', 0x3765: 'VH_JSR_HANDLER', 0x3780: 'VH_NEXT',
    0x3788: 'VB_JET_HIT', 0x37A2: 'VB_FUEL', 0x37BB: 'VB_FUEL_CHECK', 0x37C0: 'VB_FUEL_OUT', 0x37CF: 'VB_HUD_FUEL',
    0x37DD: 'VB_HUD_JETS', 0x37E6: 'VB_HUD_JET', 0x37F9: 'VB_HUD_SCORE', 0x380D: 'VB_END', 0x3813: 'VBI_IDLE',
    0x381A: 'JET_PROBE', 0x3820: 'JP_LOOP', 0x382B: 'JP_DIE',
    0x3831: 'Q0', 0x3832: 'Q1', 0x3840: 'Q2', 0x384E: 'Q3',
    0x385C: 'PUT_EXPLOSION', 0x3873: 'HIT_FUEL', 0x3896: 'HF_CAP', 0x38A1: 'HIT_AMMO', 0x38B8: 'HIT_REPAIR',
    0x38CB: 'HIT_SOFT', 0x38D3: 'HIT_TANK_R', 0x38E5: 'HIT_TANK_L', 0x3903: 'HIT_HARD', 0x390C: 'HH_COLUMN',
    0x391C: 'ADD_SCORE', 0x3936: 'CELL_ADDR', 0x3967: 'PUT_BCD', 0x3970: 'PUT_DIGIT', 0x3979: 'ADD_PTR',
    0x3989: 'VAR_UNUSED', 0x398A: 'VSCROL_CTR', 0x398B: 'ROW_TOGGLE', 0x398C: 'PARITY', 0x398D: 'FLASH',
    0x398E: 'SND_SHELL', 0x398F: 'SND_SPLASH', 0x3990: 'SND_SHOT', 0x3991: 'SND_DEATH', 0x3992: 'JET_X',
    0x3993: 'MISSILE_X', 0x3997: 'MISSILE_Y', 0x399B: 'TRIG_PREV', 0x399C: 'HIT_CHAR', 0x399D: 'DEATH',
    0x399E: 'FUEL', 0x399F: 'FUEL_HI', 0x39A0: 'JETS', 0x39A1: 'SCORE', 0x39A2: 'SCORE_1', 0x39A3: 'SCORE_2',
    0x39A4: 'PAUSED',
    0x39A5: 'COLOURS', 0x39AE: 'MISSILE_MASKS', 0x39B2: 'JET_SHAPE0', 0x39BF: 'JET_SHAPE1',
    0x39CB: 'TILE_CHARS', 0x39D3: 'TILE_TL', 0x39DB: 'TILE_TR', 0x39E3: 'TILE_BL', 0x39EB: 'TILE_BR',
    0x39F3: 'EXPL_FRAMES', 0x39FB: 'HIT_CHARS', 0x3A2F: 'QUADRANT_TAB', 0x3A37: 'HIT_HANDLERS',
    0x3A9F: 'DEADLY', 0x3AAC: 'SCAN_CHARS', 0x3AC8: 'SCAN_HANDLERS',
    0x3B00: 'DL_GAME', 0x3B22: 'DL_TITLE',
    0x3B42: 'SCREEN-1', 0x3B43: 'SCREEN', 0x3B44: 'SCREEN+1', 0x3B62: 'ROW_M1-1', 0x3B63: 'ROW_M1', 0x3B83: 'ROW_0',
    0x3001: 'INIT+1', 0x33E1: 'SC_JSR+1', 0x33E2: 'SC_JSR+2', 0x3763: 'VH_JSR_QUADRANT+1',
    0x3764: 'VH_JSR_QUADRANT+2', 0x3766: 'VH_JSR_HANDLER+1', 0x3767: 'VH_JSR_HANDLER+2',
    0x3AC9: 'SCAN_HANDLERS+1', 0x3A30: 'QUADRANT_TAB+1', 0x3A38: 'HIT_HANDLERS+1',
    0x3E03: 'ROW_20', 0x3E43: 'HUD', 0x3E48: 'HUD_FUEL', 0x3E53: 'HUD_JETS', 0x3E5D: 'HUD_SCORE',
    0x3E63: 'TITLE_TEXT', 0x3F23: 'BOARD_END', 0x3F25: 'BOARD',
    0x2AFF: 'MISSILES-1', 0x2B00: 'MISSILES', 0x2B28: 'MISSILES+40', 0x2C00: 'PLAYER0', 0x2CB0: 'PLAYER0+176',
    0x2D00: 'PLAYER1', 0x2DB0: 'PLAYER1+176', 0x2E00: 'PLAYER2', 0x2F00: 'PLAYER3',
    0x3C43: 'SCREEN+256', 0x3D43: 'SCREEN+512',
    0xD000: 'HPOSP0', 0xD001: 'HPOSP1', 0xD004: 'HPOSM0', 0xD016: 'COLPF0', 0xD017: 'COLPF1', 0xD018: 'COLPF2',
    0xD019: 'COLPF3', 0xD01D: 'GRACTL', 0xD200: 'AUDF1', 0xD201: 'AUDC1', 0xD202: 'AUDF2', 0xD203: 'AUDC2',
    0xD204: 'AUDF3', 0xD205: 'AUDC3', 0xD206: 'AUDF4', 0xD207: 'AUDC4', 0xD208: 'AUDCTL', 0xD20A: 'RANDOM',
    0xD20F: 'SKCTL', 0xD405: 'VSCROL', 0xD407: 'PMBASE', 0xD409: 'CHBASE', 0xD40A: 'WSYNC', 0xD40E: 'NMIEN',
    0x0200: 'VDSLST', 0x0201: 'VDSLST+1', 0x022F: 'SDMCTL', 0x0230: 'SDLSTL', 0x0231: 'SDLSTH', 0x026F: 'GPRIOR',
    0x0278: 'STICK0', 0x0284: 'STRIG0', 0x02C0: 'PCOLR0', 0x02C1: 'PCOLR1', 0x02C5: 'COLOR1', 0x02C6: 'COLOR2',
    0x02C8: 'COLOR4', 0x02F4: 'CHBAS', 0x02FC: 'CH',
    0x0340: 'ICHID', 0x0342: 'ICCOM', 0x0344: 'ICBAL', 0x0345: 'ICBAH', 0x0348: 'ICBLL', 0x0349: 'ICBLH',
    0xE456: 'CIOV', 0xE45C: 'SETVBV', 0xE462: 'XITVBV',
}
ZP = {0x14: 'RTCLOK', 0x4D: 'ATRACT', 0xB0: 'SCAN_PTR', 0xB1: 'SCAN_PTR+1', 0xB4: 'ROW_PTR', 0xB5: 'ROW_PTR+1',
      0xB6: 'CELL', 0xB7: 'CELL+1'}

C = {  # comments
    0x3000: 'INITAD. Find the IOCB the DOS loader is reading this file with (ICHID open, last ICCOM = GET)',
    0x3017: 'read the rest of the file (the board) to BOARD ($3F25), up to the display list',
    0x3032: 'CIO GET; ICBLL/H return the byte count',
    0x3035: 'BOARD_END = BOARD + count - 16 = address of the last 16-byte row (the starting row)',
    0x3057: 'no board at all: make one blank row',
    0x306D: 'INIT becomes JMP RUN; close the channel and FALL THROUGH into RUN: INIT never returns to the loader',
    0x3081: 'the last instruction of INIT: no RTS follows',
    0x3084: 'RUNAD. Title screen: COLOR1/2/4 = $10, narrow playfield + PM DMA, DL_TITLE, idle VBI',
    0x30B3: 'silence GTIA/POKEY registers; OS charset',
    0x30C5: 'text fades in: COLOR1 luminance 0..14, 3 frames each (45 frames)',
    0x30D8: 'wait for the trigger pressed, then released',
    0x30E2: 'PM base $2800, single-line players; GPRIOR $31 = multicolour players, missiles as 5th player',
    0x30FB: 'clear SCREEN $3B43-$3E42 (24 rows of 32) and PM memory $2B00-$2FFF',
    0x3119: 'the jet: 13 bytes into player 0 and player 1 at y=$B0',
    0x312A: 'PCOLR0-3, COLOR0-4 from COLOURS',
    0x3135: 'DL_GAME, DLI vector, NMIEN = DLI+VBI, game VBI, charset $2400, POKEY on',
    0x3166: 'zero VAR_UNUSED..SCORE_2 (27 bytes); JET_X = $70; MISSILE_Y all 0 (the $2F is overwritten); JETS = 2; FUEL = 099',
    0x318E: 'ROW_PTR = BOARD_END; load the first (bottom) row into rows -2/-1',
    0x31A0: 'once per frame: wait for RTCLOK to change',
    0x31A6: 'ESC: fade out and restart from the title',
    0x31B0: 'space: pause until the joystick moves',
    0x31B7: 'scroll one scanline (two if the stick is up), then run the object scan',
    0x31BA: 'jet colours: PCOLR0 = 4, PCOLR1 = 8 (multicolour overlap = $0C)',
    0x31C4: 'A = frame+1; if the scan spilt into the next frame, wait for the one after',
    0x31D2: 'while FLASH > 0 the jet is drawn in $0A / $64 and cannot be hit again',
    0x31DC: 'dead load (the assembler left it): PCOLR1 gets $64',
    0x31E6: 'DEATH set by the VBI (collision or fuel out)?',
    0x31F0: 'hit while flashing: ignored',
    0x31F5: 'no spare jet left -> game over',
    0x31FA: 'lose a jet: FLASH = 50 frames, death sound',
    0x320A: 'JETS becomes $FF (the HUD then shows no jets); falls into the fade',
    0x320D: 'ESC / game over: idle VBI, three tones fade out with the colours, then RUN (title)',
    0x3237: 'Y = 15,13,..,1: AUDC1-3 = Y; every colour with luminance >= Y is dimmed to Y; 3 frames',
    0x326A: 'back to the title screen',
    0x326D: 'PAUSED = $FF stops the VBI logic; wait for any joystick direction',
    0x3288: 'VSCROL_CTR-- (twice with the stick up); VSCROL = it; on -1: wrap to 7 and shift a char row',
    0x32A8: 'move rows -2..18 down to -1..19 (32 bytes each, 21 rows)',
    0x332E: 'rows 20-21 blank',
    0x3338: 'every second shift: load the next board row into rows -2/-1',
    0x3343: 'if byte 15 of the row is an EOL the pointer is one too high (rows are 16 + EOL): step back',
    0x3358: 'cells 15..0 (Y), screen chars X = 2*cell+1 .. : look the character up in TILE_CHARS (7..1, else 0)',
    0x336A: 'a tank (TILE_TL >= $48) is not placed when the top-left char of the cell to its right is set',
    0x3376: '2x2 chars from TILE_TL/TR/BL/BR into rows -2 (top) and -1 (bottom)',
    0x3395: 'ROW_PTR -= 16 (the EOL check above makes it 17); below BOARD -> back to the last row: the board cycles',
    0x33B7: 'object scan: every char of rows -1..19 (SCAN_PTR = $3B63..$3E02); chars < $15 are inert',
    0x33C7: 'SCAN_CHARS[27..1]; no match -> X = 0 -> NEXT_CHAR (so the following char is skipped too)',
    0x33D1: 'self-modifying JSR to SCAN_HANDLERS[X]',
    0x33E3: 'SCAN_PTR++ (handlers that moved it are not compensated)',
    0x33F3: 'PARITY ^= $FF: explosions animate every other scan',
    0x33FC: 'tank facing right, phases $48 $4B $4E $51: next phase (2 px right) in place',
    0x340A: 'phase 3 done: the char right of the 3-char group (top and bottom) must be empty',
    0x3416: 'clear the leftmost column, SCAN_PTR++, draw phase 0 there',
    0x342E: 'blocked: become a left-facing tank, phase 0 ($54), in place',
    0x3435: 'tank facing left, phases $54 $57 $5A $5D: next phase (2 px left) in place',
    0x3443: 'phase 3 done: SCAN_PTR--; the new leftmost column (top and bottom) must be empty',
    0x345C: 'clear the old rightmost column (+3), draw phase 0 at SCAN_PTR',
    0x346D: 'blocked: SCAN_PTR++ back, become a right-facing tank ($48) in place',
    0x347B: 'bottom-left char of a phase-2 tank ($6E right, $7A left): RANDOM & 7 == 0 -> try to drop a shell',
    0x3483: 'the two chars below the middle column (+$21, +$41) must be empty',
    0x348E: 'shell $15/$16 two rows below the tank, shell sound',
    0x34A3: 'shell $15/$17/$19/$1B (top) with $16/$18/$1A/$1C below: 2 px down per scan',
    0x34B8: 'past $1D: if the char two rows down is set -> splash, else move the pair one row down',
    0x34D1: 'splash $1F one row down, clear, splash sound',
    0x34E2: 'splash animation $1F..$23, then empty',
    0x34F2: 'explosion $24/$28/../$3C (2x2): advance every other scan (PARITY)',
    0x350D: 'after $3C: clear the 2x2',
    0x351E: 'next frame: f, f+1 top row, f+2, f+3 bottom row',
    0x3539: 'default handler and the tail of most others: SCAN_PTR++',
    0x3540: 'A = phase base, Y = offset: 3 chars A..A+2 at SCAN_PTR+Y and A+$20.. one row below',
    0x3559: 'DLI on the last-but-one scroll row: after VSCROL+1 lines set COLPF0-3 = 0 (hides the partial row)',
    0x3584: 'DLI before the status line: COLPF2 = 2, OS charset, COLPF1 = $0E; next DLI = DLI_SCROLL_END',
    0x35AA: 'unreferenced copy of DLI_STATUS without the re-vectoring',
    0x35C3: 'deferred VBI: VSCROL, ATRACT off, then the four sound channels',
    0x35CD: 'channel 1: shell dropped: AUDF1 = 10, AUDC1 = SND_SHELL (17-bit noise), volume 1..9 rising, then off',
    0x35EF: 'channel 2: splash/explosion: every other frame AUDC2 = $20 | v, AUDF2 = v + $DC, v = 15..1',
    0x361B: 'channel 3: shot: AUDF3 = v (from $B0 down, pitch rising), AUDC3 = $E0 | (v-$30)/8, off at 0',
    0x363B: 'channel 4: jet hit: every 4 frames AUDC4 = $C0 | v (4-bit noise), AUDF4 = 10, v = 15..1',
    0x365D: 'paused: nothing else',
    0x3665: 'stick right: JET_X++ up to $B9; left: JET_X-- down to $40',
    0x3687: 'trigger just pressed (was released last frame)?',
    0x3691: 'a free missile slot (MISSILE_X = 0)? Y = 3..0',
    0x369E: 'missile at JET_X+2, y = $B0; shot sound restarts at $B0',
    0x36B1: 'reads the char under the new missile into HIT_CHAR ...',
    0x36C5: '... but both branches go to VB_JET: the code below is unreachable',
    0x36DA: 'HPOSP0/1 = JET_X',
    0x36E3: 'clear missile memory y = $29..$D8',
    0x36ED: 'each missile: HPOSM, y--, 2 pixels at y-1/y (mask by missile number); y < $30 -> slot free, y = $2F',
    0x3716: 'each active missile: the char under it (CELL_ADDR); HIT_CHARS[51..0] -> quadrant fix + HIT_HANDLERS',
    0x3742: 'X & 3 = quadrant of the 2x2 object; CELL -> its top-left',
    0x3768: 'shot sound off, splash sound = 15, the missile is freed',
    0x3788: 'the jet: the 2x2 chars at (JET_X, y = $B4): walls, shells, tanks kill',
    0x37A2: 'every 32 frames FUEL -= 1 (BCD, 3 digits)',
    0x37BB: 'FUEL below 0: DEATH, FUEL = 099',
    0x37CF: 'HUD: fuel (3 digits at +5), jets (3 icons $6F at +16, $54 blank), score (6 digits at +26)',
    0x380D: 'TRIG_PREV = STRIG0; attract mode off',
    0x3813: 'deferred VBI on the title screen and during the fade: attract mode off only',
    0x381A: 'A = char at CELL+Y: >= $48 (tanks) or in DEADLY (walls, shells) -> DEATH',
    0x3831: 'quadrant 0: nothing', 0x3832: 'quadrant 1: CELL -= 1', 0x3840: 'quadrant 2: CELL -= 32',
    0x384E: 'quadrant 3: CELL -= 33',
    0x385C: 'explosion frame 0 ($24 $25 / $26 $27) at CELL',
    0x3873: 'fuel tile: explosion, +20 points, FUEL += 499 (BCD), capped at 999',
    0x38A1: 'ammunition dump: explosion, +100 points',
    0x38B8: 'repair: explosion, +30 points, a spare jet back (max 2)',
    0x38CB: 'soft wall: explosion, +15 points',
    0x38D3: 'tank facing right: explosion over the 2x2, clear the third column, +55 points',
    0x38E5: 'tank facing left (2x2 at $55): explosion, clear the blank column left of it, +55 points',
    0x3903: 'hard wall: splash $1F in the row below the wall (hit from below) or in its bottom row, splash sound',
    0x391C: 'SCORE += A (BCD), three bytes',
    0x3936: 'CELL = ROW_M1 + ((Y-41) & ~7) * 4 + (X-63) / 4: PM coordinates to the screen char',
    0x3967: 'two BCD digits at HUD+X (X += 2)', 0x3970: 'one digit: screen code $10 + nibble',
    0x3979: 'zero-page pointer at Y += A',
    0x3989: 'never read', 0x398A: 'fine scroll 7..0', 0x398B: 'load a row every second shift',
    0x398C: 'toggles every scan', 0x398D: 'frames left of the hit flash (50)',
    0x3992: 'jet x $40..$B9', 0x3993: 'x of missiles 0..3 (0 = free)', 0x3997: 'y of missiles 0..3',
    0x399E: 'fuel: BCD, low byte first', 0x39A0: 'spare jets 0..2', 0x39A1: 'score: BCD, low byte first',
    0x39A5: 'PCOLR0-3, COLOR0-4', 0x39AE: 'missile 0..3 pixel masks', 0x39B2: 'player 0 shape', 0x39BF: 'player 1 shape',
    0x39CB: '[0] unused, then # " % $ ! < >', 0x39D3: 'top-left char per tile', 0x39DB: 'top-right',
    0x39E3: 'bottom-left', 0x39EB: 'bottom-right', 0x39F3: 'explosion frame bases, then 0',
    0x39FB: '52 chars a shot can hit: soft wall, fuel, ammo, repair, right tank x4 phases, left tank x4, hard wall',
    0x3A2F: 'quadrant fix routines', 0x3A37: 'HIT handler per HIT_CHARS entry',
    0x3A9F: 'chars that kill the jet besides tanks: walls and shells',
    0x3AAC: '[0] never matched; tanks, shell frames, splash frames, explosion frames',
    0x3AC8: 'SCAN handler per SCAN_CHARS entry',
    0x3B00: 'game display list: 40 blank lines, 20 x ANTIC 4 with VSCROL from ROW_0, DLI on row 18, blank+DLI, ANTIC 2 HUD',
    0x3B22: 'title display list: 64 blank lines, 6 x ANTIC 2 from TITLE_TEXT, 88 blank lines, ANTIC 2 HUD',
}

QUADRANT_TAB, HIT_HANDLERS, SCAN_HANDLERS = 0x3A2F, 0x3A37, 0x3AC8


def load_obj(path: Path, mpu: MPU) -> list[tuple[int, int]]:
    data = path.read_bytes()
    segs, p = [], 0
    while p + 4 <= len(data):
        if data[p:p + 2] == b'\xff\xff':
            p += 2
            continue
        start, end = struct.unpack('<HH', data[p:p + 4])
        p += 4
        for i, b in enumerate(data[p:p + end - start + 1]):
            mpu.memory[start + i] = b
        segs.append((start, end))
        p += end - start + 1
    return segs


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else 'thejet.obj')
    mpu = MPU()
    segs = load_obj(src, mpu)
    dis = Disassembler(mpu)
    code_ranges = [(s, e) for s, e in segs if s == 0x3000]
    LOAD, END = code_ranges[0][0], code_ranges[0][1] + 1

    def word(a: int) -> int:
        return mpu.memory[a] | (mpu.memory[a + 1] << 8)

    entries = [0x3000, 0x3084, 0x35C3, 0x3813, 0x3559, 0x3584, 0x35AA]
    entries += [word(QUADRANT_TAB + 2 * k) for k in range(4)]
    entries += [word(HIT_HANDLERS + 2 * k) for k in range(52)]
    entries += [word(SCAN_HANDLERS + 2 * k) for k in range(28)]

    code: dict[int, tuple[int, str]] = {}
    labels: dict[int, str] = {}
    queue = list(dict.fromkeys(entries))
    BR = {0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0}

    def tgt(t: str) -> int | None:
        p = t.split()
        return int(p[1][1:], 16) if len(p) > 1 and p[1].startswith('$') and len(p[1]) == 5 else None

    seen: set[int] = set()
    while queue:
        pc = queue.pop()
        while LOAD <= pc < END and pc not in seen:
            n, t = dis.instruction_at(pc)
            op = mpu.memory[pc]
            m = t.split()[0]
            if m == 'BRK' or t.startswith('???'):
                break
            seen.add(pc)
            code[pc] = (n, t)
            if op in BR:
                a = tgt(t)
                if a is not None:
                    labels.setdefault(a, f'L{a:04X}')
                    queue.append(a)
                pc += n
            elif m == 'JMP':
                if '(' in t:
                    break
                a = tgt(t)
                if a is not None:
                    labels.setdefault(a, f'L{a:04X}')
                    queue.append(a)
                break
            elif m == 'JSR':
                a = tgt(t)
                if a is not None:
                    labels.setdefault(a, f'S{a:04X}')
                    queue.append(a)
                pc += n
            elif m in ('RTS', 'RTI'):
                break
            else:
                pc += n
    for pc, (n, t) in code.items():
        p = t.split()
        if len(p) > 1:
            a = p[1].split(',')[0].strip('()')
            if a.startswith('$') and len(a) == 5:
                v = int(a[1:], 16)
                if LOAD <= v < END:
                    labels.setdefault(v, f'D{v:04X}')
    labels.update(NAMES)

    def sym(arg: str) -> str:
        def r4(m: re.Match[str]) -> str:
            v = int(m.group(1), 16)
            return labels.get(v, m.group(0))

        def r2(m: re.Match[str]) -> str:
            v = int(m.group(1), 16)
            return ZP.get(v, m.group(0))
        arg = re.sub(r'\$([0-9a-fA-F]{4})', r4, arg)
        return re.sub(r'(?<![0-9a-fA-F#])\$([0-9a-fA-F]{2})(?![0-9a-fA-F])', r2, arg)

    out = [f'; The Jet (Dariusz Zolna 1992, Tajemnice ATARI 6-7/92) - {src.name}',
           '; Disassembled with py65 (recursive descent from INIT, RUN, the VBIs, the DLIs and the three jump',
           '; tables). Unreached bytes are data. Segments: $2400-$27FF charset (128 glyphs, see charset.bin),',
           '; $3000-$3B42 code and tables, $3E43-$3F24 status line + title text + BOARD_END, $02E0 RUNAD/INITAD.',
           '; Screen: ANTIC mode 4, narrow playfield (32 chars per row), rows of 32 bytes from SCREEN=$3B43:',
           ';   rows -2/-1 ($3B43/$3B63) = staging area for the next board row, rows 0..19 ($3B83..) displayed',
           ';   with fine scroll VSCROL_CTR, rows 20/21 ($3E03/$3E23) blanked, HUD $3E43 (ANTIC 2, OS charset).',
           ';   A board cell is 2x2 chars. Chars: $00 empty, $01-$04 hard wall, $05-$08 soft wall, $09-$0C fuel,',
           ';   $0D-$10 ammo dump, $11-$14 repair, $15-$1E shell (falls), $1F-$23 splash, $24-$3F explosion,',
           ';   $48-$53 / $68-$73 tank facing right (4 phases x 3 columns), $54-$5F / $74-$7F tank facing left.',
           '; The jet is players 0+1 (multicolour) at y=$B0, the shots are the four missiles (5th player colour).',
           '; ZP: $14 RTCLOK, $B0/B1 SCAN_PTR, $B4/B5 ROW_PTR, $B6/B7 CELL.', '']
    pc = LOAD
    while pc < END:
        if pc in code:
            n, t = code[pc]
            raw = ' '.join(f'{mpu.memory[pc + i]:02X}' for i in range(n))
            p = t.split(None, 1)
            txt = f'{p[0]:<4}{sym(p[1])}' if len(p) == 2 else p[0]
            line = f'{pc:04X}  {raw:<9} {labels.get(pc, ""):<17} {txt:<26}'
            if pc in C:
                line += f'; {C[pc]}'
            out.append(line.rstrip())
            pc += n
        else:
            s = pc
            row = []
            while pc < END and pc not in code and len(row) < 8:
                if pc in labels and row:
                    break
                row.append(mpu.memory[pc])
                pc += 1
                if pc in labels:
                    break
            h = ' '.join(f'{b:02X}' for b in row)
            asc = ''.join(chr(b + 0x20) if b < 0x40 else chr(b) if 0x60 <= b < 0x7F else '.' for b in row)
            line = f'{s:04X}  {"":<9} {labels.get(s, ""):<17} .byte {h:<24} ; {asc}'
            if s in C:
                line += f'  ; {C[s]}'
            out.append(line)
    # the text segment as data with screen-code decoding
    for start, end in segs:
        if start == 0x3E43:
            out.append('')
            out.append(f'; ===== segment ${start:04X}-${end:04X}: status line (32 bytes), title screen (6 rows of 32,')
            out.append(';       ANTIC 2 screen codes with bit 7 = inverse; rows 0-3 draw the logo with control-graphics),')
            out.append(';       BOARD_END (2 bytes, rewritten by INIT)')
            a = start
            while a <= end:
                n = min(32, end - a + 1)
                row = [mpu.memory[a + i] for i in range(n)]
                h = ' '.join(f'{b:02X}' for b in row)
                asc = ''.join(chr((b & 0x7F) + 0x20) if (b & 0x7F) < 0x40 else chr(b & 0x7F) if (b & 0x7F) >= 0x60
                              else '.' for b in row)
                out.append(f'{a:04X}  {labels.get(a, ""):<17} .byte {h}')
                out.append(f'{"":<24} ; "{asc}"')
                a += n
    print('\n'.join(out))
    print(f'; code bytes {sum(n for n, _ in code.values())}/{END - LOAD}', file=sys.stderr)


if __name__ == '__main__':
    main()
