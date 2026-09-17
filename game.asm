; The Jet (Dariusz Zolna 1992, Tajemnice ATARI 6-7/92) - thejet.obj
; Disassembled with py65 (recursive descent from INIT, RUN, the VBIs, the DLIs and the three jump
; tables). Unreached bytes are data. Segments: $2400-$27FF charset (128 glyphs, see charset.bin),
; $3000-$3B42 code and tables, $3E43-$3F24 status line + title text + BOARD_END, $02E0 RUNAD/INITAD.
; Screen: ANTIC mode 4, narrow playfield (32 chars per row), rows of 32 bytes from SCREEN=$3B43:
;   rows -2/-1 ($3B43/$3B63) = staging area for the next board row, rows 0..19 ($3B83..) displayed
;   with fine scroll VSCROL_CTR, rows 20/21 ($3E03/$3E23) blanked, HUD $3E43 (ANTIC 2, OS charset).
;   A board cell is 2x2 chars. Chars: $00 empty, $01-$04 hard wall, $05-$08 soft wall, $09-$0C fuel,
;   $0D-$10 ammo dump, $11-$14 repair, $15-$1E shell (falls), $1F-$23 splash, $24-$3F explosion,
;   $48-$53 / $68-$73 tank facing right (4 phases x 3 columns), $54-$5F / $74-$7F tank facing left.
; The jet is players 0+1 (multicolour) at y=$B0, the shots are the four missiles (5th player colour).
; ZP: $14 RTCLOK, $B0/B1 SCAN_PTR, $B4/B5 ROW_PTR, $B6/B7 CELL.

3000  A2 70     INIT              LDX #$70                  ; INITAD. Find the IOCB the DOS loader is reading this file with (ICHID open, last ICCOM = GET)
3002  BD 40 03  IN_FIND_IOCB      LDA ICHID,X
3005  30 07                       BMI L300E
3007  BD 42 03                    LDA ICCOM,X
300A  C9 07                       CMP #$07
300C  F0 09                       BEQ IN_READ
300E  8A        L300E             TXA
300F  38                          SEC
3010  E9 10                       SBC #$10
3012  AA                          TAX
3013  D0 ED                       BNE IN_FIND_IOCB
3015  38        IN_NO_IOCB        SEC
3016  60                          RTS
3017  A9 25     IN_READ           LDA #$25                  ; read the rest of the file (the board) to BOARD ($3F25), up to the display list
3019  9D 44 03                    STA ICBAL,X
301C  A9 3F                       LDA #$3f
301E  9D 45 03                    STA ICBAH,X
3021  AD 30 02                    LDA SDLSTL
3024  38                          SEC
3025  E9 25                       SBC #$25
3027  9D 48 03                    STA ICBLL,X
302A  AD 31 02                    LDA SDLSTH
302D  E9 3F                       SBC #$3f
302F  9D 49 03                    STA ICBLH,X
3032  20 56 E4                    JSR CIOV                  ; CIO GET; ICBLL/H return the byte count
3035  BD 48 03  IN_END_PTR        LDA ICBLL,X               ; BOARD_END = BOARD + count - 16 = address of the last 16-byte row (the starting row)
3038  18                          CLC
3039  69 25                       ADC #$25
303B  8D 23 3F                    STA BOARD_END
303E  BD 49 03                    LDA ICBLH,X
3041  69 3F                       ADC #$3f
3043  8D 24 3F                    STA $3f24
3046  AD 23 3F                    LDA BOARD_END
3049  38                          SEC
304A  E9 10                       SBC #$10
304C  8D 23 3F                    STA BOARD_END
304F  AD 24 3F                    LDA $3f24
3052  E9 00                       SBC #$00
3054  8D 24 3F                    STA $3f24
3057  AD 23 3F                    LDA BOARD_END             ; no board at all: make one blank row
305A  C9 25                       CMP #$25
305C  AD 24 3F                    LDA $3f24
305F  E9 3F                       SBC #$3f
3061  B0 0A                       BCS IN_PATCH
3063  A0 0F     IN_BLANK_ROW      LDY #$0f
3065  A9 00                       LDA #$00
3067  99 25 3F  L3067             STA BOARD,Y
306A  88                          DEY
306B  10 FA                       BPL L3067
306D  A9 4C     IN_PATCH          LDA #$4c                  ; INIT becomes JMP RUN; close the channel and FALL THROUGH into RUN: INIT never returns to the loader
306F  8D 00 30                    STA INIT
3072  A9 84                       LDA #$84
3074  8D 01 30                    STA INIT+1
3077  A9 30                       LDA #$30
3079  8D 02 30                    STA IN_FIND_IOCB
307C  A9 0C                       LDA #$0c
307E  9D 42 03                    STA ICCOM,X
3081  20 56 E4                    JSR CIOV                  ; the last instruction of INIT: no RTS follows
3084  A9 10     RUN               LDA #$10                  ; RUNAD. Title screen: COLOR1/2/4 = $10, narrow playfield + PM DMA, DL_TITLE, idle VBI
3086  8D C8 02                    STA COLOR4
3089  8D C6 02                    STA COLOR2
308C  8D C5 02                    STA COLOR1
308F  A5 14                       LDA RTCLOK
3091  C5 14     RU_WAIT           CMP RTCLOK
3093  F0 FC                       BEQ RU_WAIT
3095  A9 3D                       LDA #$3d
3097  8D 2F 02                    STA SDMCTL
309A  A9 22                       LDA #$22
309C  8D 30 02                    STA SDLSTL
309F  A9 3B                       LDA #$3b
30A1  8D 31 02                    STA SDLSTH
30A4  A0 13                       LDY #$13
30A6  A2 38                       LDX #$38
30A8  A9 07                       LDA #$07
30AA  20 5C E4                    JSR SETVBV
30AD  A5 14                       LDA RTCLOK
30AF  C5 14     L30AF             CMP RTCLOK
30B1  F0 FC                       BEQ L30AF
30B3  A9 00                       LDA #$00                  ; silence GTIA/POKEY registers; OS charset
30B5  A0 07                       LDY #$07
30B7  99 00 D0  L30B7             STA HPOSP0,Y
30BA  99 00 D2                    STA AUDF1,Y
30BD  88                          DEY
30BE  10 F7                       BPL L30B7
30C0  A9 E0                       LDA #$e0
30C2  8D F4 02                    STA CHBAS
30C5  A0 00     TI_FADE_IN        LDY #$00                  ; text fades in: COLOR1 luminance 0..14, 3 frames each (45 frames)
30C7  8C C5 02  TI_STEP           STY COLOR1
30CA  A5 14                       LDA RTCLOK
30CC  18                          CLC
30CD  69 03                       ADC #$03
30CF  C5 14     TI_WAIT3          CMP RTCLOK
30D1  D0 FC                       BNE TI_WAIT3
30D3  C8                          INY
30D4  C0 0F                       CPY #$0f
30D6  90 EF                       BCC TI_STEP
30D8  AD 84 02  TI_WAIT_FIRE      LDA STRIG0                ; wait for the trigger pressed, then released
30DB  F0 FB                       BEQ TI_WAIT_FIRE
30DD  AD 84 02  TI_WAIT_RELEASE   LDA STRIG0
30E0  D0 FB                       BNE TI_WAIT_RELEASE
30E2  A9 28     GAME_INIT         LDA #$28                  ; PM base $2800, single-line players; GPRIOR $31 = multicolour players, missiles as 5th player
30E4  8D 07 D4                    STA PMBASE
30E7  A9 03                       LDA #$03
30E9  8D 1D D0                    STA GRACTL
30EC  A0 0C                       LDY #$0c
30EE  A9 00                       LDA #$00
30F0  99 00 D0  L30F0             STA HPOSP0,Y
30F3  88                          DEY
30F4  10 FA                       BPL L30F0
30F6  A9 31                       LDA #$31
30F8  8D 6F 02                    STA GPRIOR
30FB  A0 00     GI_CLEAR          LDY #$00                  ; clear SCREEN $3B43-$3E42 (24 rows of 32) and PM memory $2B00-$2FFF
30FD  98                          TYA
30FE  99 43 3B  GI_CLEAR_LOOP     STA SCREEN,Y
3101  99 43 3C                    STA SCREEN+256,Y
3104  99 43 3D                    STA SCREEN+512,Y
3107  99 00 2B                    STA MISSILES,Y
310A  99 00 2C                    STA PLAYER0,Y
310D  99 00 2D                    STA PLAYER1,Y
3110  99 00 2E                    STA PLAYER2,Y
3113  99 00 2F                    STA PLAYER3,Y
3116  88                          DEY
3117  D0 E5                       BNE GI_CLEAR_LOOP
3119  A0 0C     GI_SHAPES         LDY #$0c                  ; the jet: 13 bytes into player 0 and player 1 at y=$B0
311B  B9 B2 39  GI_SHAPES_LOOP    LDA JET_SHAPE0,Y
311E  99 B0 2C                    STA PLAYER0+176,Y
3121  B9 BF 39                    LDA JET_SHAPE1,Y
3124  99 B0 2D                    STA PLAYER1+176,Y
3127  88                          DEY
3128  10 F1                       BPL GI_SHAPES_LOOP
312A  A0 08     GI_COLOURS        LDY #$08                  ; PCOLR0-3, COLOR0-4 from COLOURS
312C  B9 A5 39  GI_COLOURS_LOOP   LDA COLOURS,Y
312F  99 C0 02                    STA PCOLR0,Y
3132  88                          DEY
3133  10 F7                       BPL GI_COLOURS_LOOP
3135  A9 00                       LDA #$00                  ; DL_GAME, DLI vector, NMIEN = DLI+VBI, game VBI, charset $2400, POKEY on
3137  8D 30 02                    STA SDLSTL
313A  A9 3B                       LDA #$3b
313C  8D 31 02                    STA SDLSTH
313F  A9 59                       LDA #$59
3141  8D 00 02                    STA VDSLST
3144  A9 35                       LDA #$35
3146  8D 01 02                    STA VDSLST+1
3149  A9 C0                       LDA #$c0
314B  8D 0E D4                    STA NMIEN
314E  A0 C3                       LDY #$c3
3150  A2 35                       LDX #$35
3152  A9 07                       LDA #$07
3154  20 5C E4                    JSR SETVBV
3157  A9 24                       LDA #$24
3159  8D F4 02                    STA CHBAS
315C  A9 03                       LDA #$03
315E  8D 0F D2                    STA SKCTL
3161  A9 00                       LDA #$00
3163  8D 08 D2                    STA AUDCTL
3166  A0 1A     GI_VARS           LDY #$1a                  ; zero VAR_UNUSED..SCORE_2 (27 bytes); JET_X = $70; MISSILE_Y all 0 (the $2F is overwritten); JETS = 2; FUEL = 099
3168  A9 00                       LDA #$00
316A  99 89 39  GI_VARS_LOOP      STA VAR_UNUSED,Y
316D  88                          DEY
316E  10 FA                       BPL GI_VARS_LOOP
3170  A9 70                       LDA #$70
3172  8D 92 39                    STA JET_X
3175  A0 03                       LDY #$03
3177  A9 2F     GI_MISSILES       LDA #$2f
3179  99 97 39                    STA MISSILE_Y,Y
317C  A9 00                       LDA #$00
317E  99 97 39                    STA MISSILE_Y,Y
3181  88                          DEY
3182  10 F3                       BPL GI_MISSILES
3184  A9 02                       LDA #$02
3186  8D A0 39                    STA JETS
3189  A9 99                       LDA #$99
318B  8D 9E 39                    STA FUEL
318E  AD 23 3F                    LDA BOARD_END             ; ROW_PTR = BOARD_END; load the first (bottom) row into rows -2/-1
3191  85 B4                       STA ROW_PTR
3193  AD 24 3F                    LDA $3f24
3196  85 B5                       STA ROW_PTR+1
3198  20 43 33                    JSR LOAD_ROW
319B  A9 FF                       LDA #$ff
319D  8D FC 02                    STA CH
31A0  A5 14     MAIN_LOOP         LDA RTCLOK                ; once per frame: wait for RTCLOK to change
31A2  C5 14     ML_WAIT           CMP RTCLOK
31A4  F0 FC                       BEQ ML_WAIT
31A6  AD FC 02                    LDA CH                    ; ESC: fade out and restart from the title
31A9  C9 1C                       CMP #$1c
31AB  D0 03                       BNE ML_SPACE
31AD  4C 0D 32                    JMP FADE_OUT
31B0  C9 21     ML_SPACE          CMP #$21                  ; space: pause until the joystick moves
31B2  D0 03                       BNE ML_FRAME
31B4  20 6D 32                    JSR PAUSE
31B7  20 88 32  ML_FRAME          JSR SCROLL                ; scroll one scanline (two if the stick is up), then run the object scan
31BA  A9 04                       LDA #$04                  ; jet colours: PCOLR0 = 4, PCOLR1 = 8 (multicolour overlap = $0C)
31BC  8D C0 02                    STA PCOLR0
31BF  A9 08                       LDA #$08
31C1  8D C1 02                    STA PCOLR1
31C4  A5 14                       LDA RTCLOK                ; A = frame+1; if the scan spilt into the next frame, wait for the one after
31C6  18                          CLC
31C7  69 01                       ADC #$01
31C9  48                          PHA
31CA  20 B7 33                    JSR SCAN
31CD  68                          PLA
31CE  C5 14     ML_WAIT_SCAN      CMP RTCLOK
31D0  F0 FC                       BEQ ML_WAIT_SCAN
31D2  AD 8D 39  ML_FLASH          LDA FLASH                 ; while FLASH > 0 the jet is drawn in $0A / $64 and cannot be hit again
31D5  F0 0F                       BEQ ML_DEATH
31D7  A9 0A                       LDA #$0a
31D9  8D C0 02                    STA PCOLR0
31DC  A9 0C                       LDA #$0c                  ; dead load (the assembler left it): PCOLR1 gets $64
31DE  A9 64                       LDA #$64
31E0  8D C1 02                    STA PCOLR1
31E3  CE 8D 39                    DEC FLASH
31E6  AD 9D 39  ML_DEATH          LDA DEATH                 ; DEATH set by the VBI (collision or fuel out)?
31E9  F0 B5                       BEQ MAIN_LOOP
31EB  A9 00     ML_DIE            LDA #$00
31ED  8D 9D 39                    STA DEATH
31F0  AD 8D 39                    LDA FLASH                 ; hit while flashing: ignored
31F3  D0 AB                       BNE MAIN_LOOP
31F5  AD A0 39  ML_LIVES          LDA JETS                  ; no spare jet left -> game over
31F8  F0 10                       BEQ GAME_OVER
31FA  CE A0 39  ML_LOSE_JET       DEC JETS                  ; lose a jet: FLASH = 50 frames, death sound
31FD  A9 32                       LDA #$32
31FF  8D 8D 39                    STA FLASH
3202  A9 0F                       LDA #$0f
3204  8D 91 39                    STA SND_DEATH
3207  4C A0 31                    JMP MAIN_LOOP
320A  CE A0 39  GAME_OVER         DEC JETS                  ; JETS becomes $FF (the HUD then shows no jets); falls into the fade
320D  A5 14     FADE_OUT          LDA RTCLOK                ; ESC / game over: idle VBI, three tones fade out with the colours, then RUN (title)
320F  C5 14     FO_WAIT           CMP RTCLOK
3211  F0 FC                       BEQ FO_WAIT
3213  A0 13                       LDY #$13
3215  A2 38                       LDX #$38
3217  A9 07                       LDA #$07
3219  20 5C E4                    JSR SETVBV
321C  A9 00                       LDA #$00
321E  A0 07                       LDY #$07
3220  99 00 D2  FO_SILENCE        STA AUDF1,Y
3223  88                          DEY
3224  10 FA                       BPL FO_SILENCE
3226  A9 14                       LDA #$14
3228  8D 00 D2                    STA AUDF1
322B  A9 64                       LDA #$64
322D  8D 02 D2                    STA AUDF2
3230  A9 C8                       LDA #$c8
3232  8D 04 D2                    STA AUDF3
3235  A0 0F                       LDY #$0f
3237  8C 8C 39  FO_STEP           STY PARITY                ; Y = 15,13,..,1: AUDC1-3 = Y; every colour with luminance >= Y is dimmed to Y; 3 frames
323A  8C 01 D2                    STY AUDC1
323D  8C 03 D2                    STY AUDC2
3240  8C 05 D2                    STY AUDC3
3243  A2 07                       LDX #$07
3245  BD C0 02  FO_COLOUR         LDA PCOLR0,X
3248  29 0F                       AND #$0f
324A  CD 8C 39                    CMP PARITY
324D  90 0B                       BCC FO_NEXT
324F  BD C0 02                    LDA PCOLR0,X
3252  29 F0                       AND #$f0
3254  0D 8C 39                    ORA PARITY
3257  9D C0 02                    STA PCOLR0,X
325A  CA        FO_NEXT           DEX
325B  10 E8                       BPL FO_COLOUR
325D  A5 14                       LDA RTCLOK
325F  18                          CLC
3260  69 03                       ADC #$03
3262  C5 14     FO_WAIT3          CMP RTCLOK
3264  D0 FC                       BNE FO_WAIT3
3266  88                          DEY
3267  88                          DEY
3268  10 CD                       BPL FO_STEP
326A  4C 84 30                    JMP RUN                   ; back to the title screen
326D  A9 FF     PAUSE             LDA #$ff                  ; PAUSED = $FF stops the VBI logic; wait for any joystick direction
326F  8D A4 39                    STA PAUSED
3272  A5 14                       LDA RTCLOK
3274  C5 14     PA_WAIT           CMP RTCLOK
3276  F0 FC                       BEQ PA_WAIT
3278  AD 78 02                    LDA STICK0
327B  C9 0F                       CMP #$0f
327D  F0 EE                       BEQ PAUSE
327F  A9 00                       LDA #$00
3281  8D A4 39                    STA PAUSED
3284  8D FC 02                    STA CH
3287  60                          RTS
3288  CE 8A 39  SCROLL            DEC VSCROL_CTR            ; VSCROL_CTR-- (twice with the stick up); VSCROL = it; on -1: wrap to 7 and shift a char row
328B  AD 78 02                    LDA STICK0
328E  29 01                       AND #$01
3290  D0 03                       BNE L3295
3292  CE 8A 39                    DEC VSCROL_CTR
3295  AD 8A 39  L3295             LDA VSCROL_CTR
3298  8D 05 D4                    STA VSCROL
329B  30 03                       BMI SC_SHIFT
329D  4C 42 33                    JMP RTS1
32A0  A9 07     SC_SHIFT          LDA #$07
32A2  8D 8A 39                    STA VSCROL_CTR
32A5  8D 05 D4                    STA VSCROL
32A8  A0 1F                       LDY #$1f                  ; move rows -2..18 down to -1..19 (32 bytes each, 21 rows)
32AA  B9 C3 3D  SC_COPY           LDA $3dc3,Y
32AD  99 E3 3D                    STA $3de3,Y
32B0  B9 A3 3D                    LDA $3da3,Y
32B3  99 C3 3D                    STA $3dc3,Y
32B6  B9 83 3D                    LDA $3d83,Y
32B9  99 A3 3D                    STA $3da3,Y
32BC  B9 63 3D                    LDA $3d63,Y
32BF  99 83 3D                    STA $3d83,Y
32C2  B9 43 3D                    LDA SCREEN+512,Y
32C5  99 63 3D                    STA $3d63,Y
32C8  B9 23 3D                    LDA $3d23,Y
32CB  99 43 3D                    STA SCREEN+512,Y
32CE  B9 03 3D                    LDA $3d03,Y
32D1  99 23 3D                    STA $3d23,Y
32D4  B9 E3 3C                    LDA $3ce3,Y
32D7  99 03 3D                    STA $3d03,Y
32DA  B9 C3 3C                    LDA $3cc3,Y
32DD  99 E3 3C                    STA $3ce3,Y
32E0  B9 A3 3C                    LDA $3ca3,Y
32E3  99 C3 3C                    STA $3cc3,Y
32E6  B9 83 3C                    LDA $3c83,Y
32E9  99 A3 3C                    STA $3ca3,Y
32EC  B9 63 3C                    LDA $3c63,Y
32EF  99 83 3C                    STA $3c83,Y
32F2  B9 43 3C                    LDA SCREEN+256,Y
32F5  99 63 3C                    STA $3c63,Y
32F8  B9 23 3C                    LDA $3c23,Y
32FB  99 43 3C                    STA SCREEN+256,Y
32FE  B9 03 3C                    LDA $3c03,Y
3301  99 23 3C                    STA $3c23,Y
3304  B9 E3 3B                    LDA $3be3,Y
3307  99 03 3C                    STA $3c03,Y
330A  B9 C3 3B                    LDA $3bc3,Y
330D  99 E3 3B                    STA $3be3,Y
3310  B9 A3 3B                    LDA $3ba3,Y
3313  99 C3 3B                    STA $3bc3,Y
3316  B9 83 3B                    LDA ROW_0,Y
3319  99 A3 3B                    STA $3ba3,Y
331C  B9 63 3B                    LDA ROW_M1,Y
331F  99 83 3B                    STA ROW_0,Y
3322  B9 43 3B                    LDA SCREEN,Y
3325  99 63 3B                    STA ROW_M1,Y
3328  88                          DEY
3329  30 03                       BMI SC_CLEAR_BOTTOM
332B  4C AA 32                    JMP SC_COPY
332E  A0 3F     SC_CLEAR_BOTTOM   LDY #$3f                  ; rows 20-21 blank
3330  A9 00                       LDA #$00
3332  99 03 3E  SC_CLEAR_LOOP     STA ROW_20,Y
3335  88                          DEY
3336  10 FA                       BPL SC_CLEAR_LOOP
3338  AD 8B 39  SC_TOGGLE         LDA ROW_TOGGLE            ; every second shift: load the next board row into rows -2/-1
333B  49 FF                       EOR #$ff
333D  8D 8B 39                    STA ROW_TOGGLE
3340  F0 01                       BEQ LOAD_ROW
3342  60        RTS1              RTS
3343  A0 0F     LOAD_ROW          LDY #$0f                  ; if byte 15 of the row is an EOL the pointer is one too high (rows are 16 + EOL): step back
3345  B1 B4                       LDA (ROW_PTR),Y
3347  C9 9B                       CMP #$9b
3349  D0 0D                       BNE LR_START
334B  A5 B4                       LDA ROW_PTR
334D  38                          SEC
334E  E9 01                       SBC #$01
3350  85 B4                       STA ROW_PTR
3352  A5 B5                       LDA ROW_PTR+1
3354  E9 00                       SBC #$00
3356  85 B5                       STA ROW_PTR+1
3358  A0 0F     LR_START          LDY #$0f                  ; cells 15..0 (Y), screen chars X = 2*cell+1 .. : look the character up in TILE_CHARS (7..1, else 0)
335A  A2 1F                       LDX #$1f
335C  98        LR_CELL           TYA
335D  48                          PHA
335E  B1 B4                       LDA (ROW_PTR),Y
3360  A0 07                       LDY #$07
3362  D9 CB 39  LR_MATCH          CMP TILE_CHARS,Y
3365  F0 03                       BEQ LR_TILE
3367  88                          DEY
3368  D0 F8                       BNE LR_MATCH
336A  B9 D3 39  LR_TILE           LDA TILE_TL,Y             ; a tank (TILE_TL >= $48) is not placed when the top-left char of the cell to its right is set
336D  C9 48                       CMP #$48
336F  90 05                       BCC LR_PUT
3371  BD 44 3B                    LDA SCREEN+1,X
3374  D0 18                       BNE LR_NEXT
3376  B9 D3 39  LR_PUT            LDA TILE_TL,Y             ; 2x2 chars from TILE_TL/TR/BL/BR into rows -2 (top) and -1 (bottom)
3379  9D 42 3B                    STA SCREEN-1,X
337C  B9 DB 39                    LDA TILE_TR,Y
337F  9D 43 3B                    STA SCREEN,X
3382  B9 E3 39                    LDA TILE_BL,Y
3385  9D 62 3B                    STA ROW_M1-1,X
3388  B9 EB 39                    LDA TILE_BR,Y
338B  9D 63 3B                    STA ROW_M1,X
338E  CA        LR_NEXT           DEX
338F  CA                          DEX
3390  68                          PLA
3391  A8                          TAY
3392  88                          DEY
3393  10 C7                       BPL LR_CELL
3395  A5 B4     LR_PREV_ROW       LDA ROW_PTR               ; ROW_PTR -= 16 (the EOL check above makes it 17); below BOARD -> back to the last row: the board cycles
3397  38                          SEC
3398  E9 10                       SBC #$10
339A  85 B4                       STA ROW_PTR
339C  A5 B5                       LDA ROW_PTR+1
339E  E9 00                       SBC #$00
33A0  85 B5                       STA ROW_PTR+1
33A2  A5 B4                       LDA ROW_PTR
33A4  C9 25                       CMP #$25
33A6  A5 B5                       LDA ROW_PTR+1
33A8  E9 3F                       SBC #$3f
33AA  B0 0A                       BCS RTS2
33AC  AD 23 3F  LR_WRAP           LDA BOARD_END
33AF  85 B4                       STA ROW_PTR
33B1  AD 24 3F                    LDA $3f24
33B4  85 B5                       STA ROW_PTR+1
33B6  60        RTS2              RTS
33B7  A9 63     SCAN              LDA #$63                  ; object scan: every char of rows -1..19 (SCAN_PTR = $3B63..$3E02); chars < $15 are inert
33B9  85 B0                       STA SCAN_PTR
33BB  A9 3B                       LDA #$3b
33BD  85 B1                       STA SCAN_PTR+1
33BF  A0 00     SC_CHAR           LDY #$00
33C1  B1 B0                       LDA (SCAN_PTR),Y
33C3  C9 15                       CMP #$15
33C5  90 1C                       BCC SC_NEXT
33C7  A2 1B                       LDX #$1b                  ; SCAN_CHARS[27..1]; no match -> X = 0 -> NEXT_CHAR (so the following char is skipped too)
33C9  DD AC 3A  SC_MATCH          CMP SCAN_CHARS,X
33CC  F0 03                       BEQ SC_DISPATCH
33CE  CA                          DEX
33CF  D0 F8                       BNE SC_MATCH
33D1  8A        SC_DISPATCH       TXA                       ; self-modifying JSR to SCAN_HANDLERS[X]
33D2  0A                          ASL A
33D3  AA                          TAX
33D4  BD C8 3A                    LDA SCAN_HANDLERS,X
33D7  8D E1 33                    STA SC_JSR+1
33DA  BD C9 3A                    LDA SCAN_HANDLERS+1,X
33DD  8D E2 33                    STA SC_JSR+2
33E0  20 39 35  SC_JSR            JSR NEXT_CHAR
33E3  E6 B0     SC_NEXT           INC SCAN_PTR              ; SCAN_PTR++ (handlers that moved it are not compensated)
33E5  D0 02                       BNE SC_END_TEST
33E7  E6 B1                       INC SCAN_PTR+1
33E9  A5 B0     SC_END_TEST       LDA SCAN_PTR
33EB  C9 03                       CMP #$03
33ED  A5 B1                       LDA SCAN_PTR+1
33EF  E9 3E                       SBC #$3e
33F1  90 CC                       BCC SC_CHAR
33F3  AD 8C 39  SC_END            LDA PARITY                ; PARITY ^= $FF: explosions animate every other scan
33F6  49 FF                       EOR #$ff
33F8  8D 8C 39                    STA PARITY
33FB  60                          RTS
33FC  A0 00     H_TANK_R          LDY #$00                  ; tank facing right, phases $48 $4B $4E $51: next phase (2 px right) in place
33FE  B1 B0                       LDA (SCAN_PTR),Y
3400  18                          CLC
3401  69 03                       ADC #$03
3403  C9 54                       CMP #$54
3405  B0 03                       BCS TR_STEP
3407  4C 40 35                    JMP DRAW_TANK
340A  A0 03     TR_STEP           LDY #$03                  ; phase 3 done: the char right of the 3-char group (top and bottom) must be empty
340C  B1 B0                       LDA (SCAN_PTR),Y
340E  D0 1E                       BNE TR_TURN
3410  A0 23                       LDY #$23
3412  B1 B0                       LDA (SCAN_PTR),Y
3414  D0 18                       BNE TR_TURN
3416  A9 00     TR_ADVANCE        LDA #$00                  ; clear the leftmost column, SCAN_PTR++, draw phase 0 there
3418  A0 00                       LDY #$00
341A  91 B0                       STA (SCAN_PTR),Y
341C  A0 20                       LDY #$20
341E  91 B0                       STA (SCAN_PTR),Y
3420  A0 B0                       LDY #$b0
3422  A9 01                       LDA #$01
3424  20 79 39                    JSR ADD_PTR
3427  A9 48                       LDA #$48
3429  A0 00                       LDY #$00
342B  4C 40 35                    JMP DRAW_TANK
342E  A9 54     TR_TURN           LDA #$54                  ; blocked: become a left-facing tank, phase 0 ($54), in place
3430  A0 00                       LDY #$00
3432  4C 40 35                    JMP DRAW_TANK
3435  A0 00     H_TANK_L          LDY #$00                  ; tank facing left, phases $54 $57 $5A $5D: next phase (2 px left) in place
3437  B1 B0                       LDA (SCAN_PTR),Y
3439  18                          CLC
343A  69 03                       ADC #$03
343C  C9 60                       CMP #$60
343E  B0 03                       BCS TL_STEP
3440  4C 40 35                    JMP DRAW_TANK
3443  A5 B0     TL_STEP           LDA SCAN_PTR              ; phase 3 done: SCAN_PTR--; the new leftmost column (top and bottom) must be empty
3445  38                          SEC
3446  E9 01                       SBC #$01
3448  85 B0                       STA SCAN_PTR
344A  A5 B1                       LDA SCAN_PTR+1
344C  E9 00                       SBC #$00
344E  85 B1                       STA SCAN_PTR+1
3450  A0 00                       LDY #$00
3452  B1 B0                       LDA (SCAN_PTR),Y
3454  D0 17                       BNE TL_TURN
3456  A0 20                       LDY #$20
3458  B1 B0                       LDA (SCAN_PTR),Y
345A  D0 11                       BNE TL_TURN
345C  A9 00     TL_ADVANCE        LDA #$00                  ; clear the old rightmost column (+3), draw phase 0 at SCAN_PTR
345E  A0 03                       LDY #$03
3460  91 B0                       STA (SCAN_PTR),Y
3462  A0 23                       LDY #$23
3464  91 B0                       STA (SCAN_PTR),Y
3466  A9 54                       LDA #$54
3468  A0 00                       LDY #$00
346A  4C 40 35                    JMP DRAW_TANK
346D  A0 B0     TL_TURN           LDY #$b0                  ; blocked: SCAN_PTR++ back, become a right-facing tank ($48) in place
346F  A9 01                       LDA #$01
3471  20 79 39                    JSR ADD_PTR
3474  A9 48                       LDA #$48
3476  A0 00                       LDY #$00
3478  4C 40 35                    JMP DRAW_TANK
347B  AD 0A D2  H_TANK_DROP       LDA RANDOM                ; bottom-left char of a phase-2 tank ($6E right, $7A left): RANDOM & 7 == 0 -> try to drop a shell
347E  29 07                       AND #$07
3480  F0 01                       BEQ TD_CHECK
3482  60                          RTS
3483  A0 21     TD_CHECK          LDY #$21                  ; the two chars below the middle column (+$21, +$41) must be empty
3485  B1 B0                       LDA (SCAN_PTR),Y
3487  A0 41                       LDY #$41
3489  11 B0                       ORA (SCAN_PTR),Y
348B  F0 01                       BEQ TD_DROP
348D  60                          RTS
348E  A0 21     TD_DROP           LDY #$21                  ; shell $15/$16 two rows below the tank, shell sound
3490  A9 15                       LDA #$15
3492  91 B0                       STA (SCAN_PTR),Y
3494  18                          CLC
3495  69 01                       ADC #$01
3497  A0 41                       LDY #$41
3499  91 B0                       STA (SCAN_PTR),Y
349B  A9 01                       LDA #$01
349D  8D 8E 39                    STA SND_SHELL
34A0  4C 39 35                    JMP NEXT_CHAR
34A3  A0 00     H_SHELL           LDY #$00                  ; shell $15/$17/$19/$1B (top) with $16/$18/$1A/$1C below: 2 px down per scan
34A5  B1 B0                       LDA (SCAN_PTR),Y
34A7  18                          CLC
34A8  69 02                       ADC #$02
34AA  C9 1E                       CMP #$1e
34AC  B0 0A                       BCS SH_ROW_END
34AE  91 B0                       STA (SCAN_PTR),Y
34B0  18                          CLC
34B1  69 01                       ADC #$01
34B3  A0 20                       LDY #$20
34B5  91 B0                       STA (SCAN_PTR),Y
34B7  60                          RTS
34B8  A0 40     SH_ROW_END        LDY #$40                  ; past $1D: if the char two rows down is set -> splash, else move the pair one row down
34BA  B1 B0                       LDA (SCAN_PTR),Y
34BC  D0 13                       BNE SH_SPLASH
34BE  A0 20     SH_MOVE           LDY #$20
34C0  A9 15                       LDA #$15
34C2  91 B0                       STA (SCAN_PTR),Y
34C4  18                          CLC
34C5  69 01                       ADC #$01
34C7  A0 40                       LDY #$40
34C9  91 B0                       STA (SCAN_PTR),Y
34CB  A0 00                       LDY #$00
34CD  98                          TYA
34CE  91 B0                       STA (SCAN_PTR),Y
34D0  60                          RTS
34D1  A9 1F     SH_SPLASH         LDA #$1f                  ; splash $1F one row down, clear, splash sound
34D3  A0 20                       LDY #$20
34D5  91 B0                       STA (SCAN_PTR),Y
34D7  A0 00                       LDY #$00
34D9  98                          TYA
34DA  91 B0                       STA (SCAN_PTR),Y
34DC  A9 0F                       LDA #$0f
34DE  8D 8F 39                    STA SND_SPLASH
34E1  60                          RTS
34E2  A0 00     H_SPLASH          LDY #$00                  ; splash animation $1F..$23, then empty
34E4  B1 B0                       LDA (SCAN_PTR),Y
34E6  18                          CLC
34E7  69 01                       ADC #$01
34E9  C9 24                       CMP #$24
34EB  90 02                       BCC L34EF
34ED  A9 00                       LDA #$00
34EF  91 B0     L34EF             STA (SCAN_PTR),Y
34F1  60                          RTS
34F2  AD 8C 39  H_EXPLOSION       LDA PARITY                ; explosion $24/$28/../$3C (2x2): advance every other scan (PARITY)
34F5  F0 03                       BEQ EX_FIND
34F7  4C 39 35                    JMP NEXT_CHAR
34FA  A0 00     EX_FIND           LDY #$00
34FC  B1 B0                       LDA (SCAN_PTR),Y
34FE  A2 07                       LDX #$07
3500  DD F3 39  EX_FIND_LOOP      CMP EXPL_FRAMES,X
3503  F0 03                       BEQ L3508
3505  CA                          DEX
3506  10 F8                       BPL EX_FIND_LOOP
3508  E8        L3508             INX
3509  E0 07                       CPX #$07
350B  90 11                       BCC EX_NEXT
350D  A9 00     EX_CLEAR          LDA #$00                  ; after $3C: clear the 2x2
350F  91 B0                       STA (SCAN_PTR),Y
3511  C8                          INY
3512  91 B0                       STA (SCAN_PTR),Y
3514  A0 20                       LDY #$20
3516  91 B0                       STA (SCAN_PTR),Y
3518  C8                          INY
3519  91 B0                       STA (SCAN_PTR),Y
351B  4C 36 35                    JMP EX_DONE
351E  BD F3 39  EX_NEXT           LDA EXPL_FRAMES,X         ; next frame: f, f+1 top row, f+2, f+3 bottom row
3521  91 B0                       STA (SCAN_PTR),Y
3523  18                          CLC
3524  69 01                       ADC #$01
3526  C8                          INY
3527  91 B0                       STA (SCAN_PTR),Y
3529  18                          CLC
352A  69 01                       ADC #$01
352C  A0 20                       LDY #$20
352E  91 B0                       STA (SCAN_PTR),Y
3530  18                          CLC
3531  69 01                       ADC #$01
3533  C8                          INY
3534  91 B0                       STA (SCAN_PTR),Y
3536  4C 39 35  EX_DONE           JMP NEXT_CHAR
3539  E6 B0     NEXT_CHAR         INC SCAN_PTR              ; default handler and the tail of most others: SCAN_PTR++
353B  D0 02                       BNE L353F
353D  E6 B1                       INC SCAN_PTR+1
353F  60        L353F             RTS
3540  48        DRAW_TANK         PHA                       ; A = phase base, Y = offset: 3 chars A..A+2 at SCAN_PTR+Y and A+$20.. one row below
3541  20 4D 35                    JSR PUT3
3544  98                          TYA
3545  18                          CLC
3546  69 1D                       ADC #$1d
3548  A8                          TAY
3549  68                          PLA
354A  18                          CLC
354B  69 20                       ADC #$20
354D  A2 02     PUT3              LDX #$02
354F  91 B0     PUT3_LOOP         STA (SCAN_PTR),Y
3551  18                          CLC
3552  69 01                       ADC #$01
3554  C8                          INY
3555  CA                          DEX
3556  10 F7                       BPL PUT3_LOOP
3558  60                          RTS
3559  48        DLI_SCROLL_END    PHA                       ; DLI on the last-but-one scroll row: after VSCROL+1 lines set COLPF0-3 = 0 (hides the partial row)
355A  98                          TYA
355B  48                          PHA
355C  A9 00                       LDA #$00
355E  AC 8A 39                    LDY VSCROL_CTR
3561  8D 0A D4  DS_WSYNC          STA WSYNC
3564  88                          DEY
3565  10 FA                       BPL DS_WSYNC
3567  8D 16 D0                    STA COLPF0
356A  8D 17 D0                    STA COLPF1
356D  8D 18 D0                    STA COLPF2
3570  8D 19 D0                    STA COLPF3
3573  A9 84                       LDA #$84
3575  A0 35                       LDY #$35
3577  8D 0A D4                    STA WSYNC
357A  8D 00 02                    STA VDSLST
357D  8C 01 02                    STY VDSLST+1
3580  68                          PLA
3581  A8                          TAY
3582  68                          PLA
3583  40                          RTI
3584  48        DLI_STATUS        PHA                       ; DLI before the status line: COLPF2 = 2, OS charset, COLPF1 = $0E; next DLI = DLI_SCROLL_END
3585  98                          TYA
3586  48                          PHA
3587  A9 02                       LDA #$02
3589  A0 E0                       LDY #$e0
358B  8D 0A D4                    STA WSYNC
358E  8D 18 D0                    STA COLPF2
3591  8C 09 D4                    STY CHBASE
3594  A9 0E                       LDA #$0e
3596  8D 17 D0                    STA COLPF1
3599  A9 59                       LDA #$59
359B  A0 35                       LDY #$35
359D  8D 0A D4                    STA WSYNC
35A0  8D 00 02                    STA VDSLST
35A3  8C 01 02                    STY VDSLST+1
35A6  68                          PLA
35A7  A8                          TAY
35A8  68                          PLA
35A9  40                          RTI
35AA  48        DLI_STATUS2       PHA                       ; unreferenced copy of DLI_STATUS without the re-vectoring
35AB  98                          TYA
35AC  48                          PHA
35AD  A9 02                       LDA #$02
35AF  A0 E0                       LDY #$e0
35B1  8D 0A D4                    STA WSYNC
35B4  8D 18 D0                    STA COLPF2
35B7  8C 09 D4                    STY CHBASE
35BA  A9 0E                       LDA #$0e
35BC  8D 17 D0                    STA COLPF1
35BF  68                          PLA
35C0  A8                          TAY
35C1  68                          PLA
35C2  40                          RTI
35C3  AD 8A 39  VBI               LDA VSCROL_CTR            ; deferred VBI: VSCROL, ATRACT off, then the four sound channels
35C6  8D 05 D4                    STA VSCROL
35C9  A9 00                       LDA #$00
35CB  85 4D                       STA ATRACT
35CD  AD 8E 39  VB_SND_SHELL      LDA SND_SHELL             ; channel 1: shell dropped: AUDF1 = 10, AUDC1 = SND_SHELL (17-bit noise), volume 1..9 rising, then off
35D0  F0 1D                       BEQ VB_SND_SPLASH
35D2  8D 01 D2                    STA AUDC1
35D5  A9 0A                       LDA #$0a
35D7  8D 00 D2                    STA AUDF1
35DA  EE 8E 39                    INC SND_SHELL
35DD  AD 8E 39                    LDA SND_SHELL
35E0  C9 0A                       CMP #$0a
35E2  90 0B                       BCC VB_SND_SPLASH
35E4  A9 00                       LDA #$00
35E6  8D 8E 39                    STA SND_SHELL
35E9  8D 00 D2                    STA AUDF1
35EC  8D 01 D2                    STA AUDC1
35EF  AD 8F 39  VB_SND_SPLASH     LDA SND_SPLASH            ; channel 2: splash/explosion: every other frame AUDC2 = $20 | v, AUDF2 = v + $DC, v = 15..1
35F2  F0 27                       BEQ VB_SND_SHOT
35F4  A5 14                       LDA RTCLOK
35F6  29 01                       AND #$01
35F8  F0 21                       BEQ VB_SND_SHOT
35FA  AD 8F 39                    LDA SND_SPLASH
35FD  09 20                       ORA #$20
35FF  8D 03 D2                    STA AUDC2
3602  AD 8F 39                    LDA SND_SPLASH
3605  18                          CLC
3606  69 DC                       ADC #$dc
3608  8D 02 D2                    STA AUDF2
360B  CE 8F 39                    DEC SND_SPLASH
360E  D0 0B                       BNE VB_SND_SHOT
3610  A9 00                       LDA #$00
3612  8D 8F 39                    STA SND_SPLASH
3615  8D 02 D2                    STA AUDF2
3618  8D 03 D2                    STA AUDC2
361B  AD 90 39  VB_SND_SHOT       LDA SND_SHOT              ; channel 3: shot: AUDF3 = v (from $B0 down, pitch rising), AUDC3 = $E0 | (v-$30)/8, off at 0
361E  F0 1B                       BEQ VB_SND_DEATH
3620  8D 04 D2                    STA AUDF3
3623  38                          SEC
3624  E9 30                       SBC #$30
3626  4A                          LSR A
3627  4A                          LSR A
3628  4A                          LSR A
3629  09 E0                       ORA #$e0
362B  8D 05 D2                    STA AUDC3
362E  CE 90 39                    DEC SND_SHOT
3631  D0 08                       BNE VB_SND_DEATH
3633  A9 00                       LDA #$00
3635  8D 04 D2                    STA AUDF3
3638  8D 05 D2                    STA AUDC3
363B  A5 14     VB_SND_DEATH      LDA RTCLOK                ; channel 4: jet hit: every 4 frames AUDC4 = $C0 | v (4-bit noise), AUDF4 = 10, v = 15..1
363D  29 03                       AND #$03
363F  D0 1C                       BNE VB_PAUSED
3641  AD 91 39                    LDA SND_DEATH
3644  F0 17                       BEQ VB_PAUSED
3646  09 C0                       ORA #$c0
3648  8D 07 D2                    STA AUDC4
364B  A9 0A                       LDA #$0a
364D  8D 06 D2                    STA AUDF4
3650  CE 91 39                    DEC SND_DEATH
3653  D0 08                       BNE VB_PAUSED
3655  A9 00                       LDA #$00
3657  8D 06 D2                    STA AUDF4
365A  8D 07 D2                    STA AUDC4
365D  AD A4 39  VB_PAUSED         LDA PAUSED                ; paused: nothing else
3660  F0 03                       BEQ VB_STICK
3662  4C 13 38                    JMP VBI_IDLE
3665  AD 78 02  VB_STICK          LDA STICK0                ; stick right: JET_X++ up to $B9; left: JET_X-- down to $40
3668  29 08                       AND #$08
366A  D0 0A                       BNE VB_LEFT
366C  AD 92 39                    LDA JET_X
366F  C9 B9                       CMP #$b9
3671  B0 03                       BCS VB_LEFT
3673  EE 92 39                    INC JET_X
3676  AD 78 02  VB_LEFT           LDA STICK0
3679  29 04                       AND #$04
367B  D0 0A                       BNE VB_FIRE
367D  AD 92 39                    LDA JET_X
3680  C9 40                       CMP #$40
3682  F0 03                       BEQ VB_FIRE
3684  CE 92 39                    DEC JET_X
3687  AD 84 02  VB_FIRE           LDA STRIG0                ; trigger just pressed (was released last frame)?
368A  D0 4E                       BNE VB_JET
368C  AD 9B 39                    LDA TRIG_PREV
368F  F0 49                       BEQ VB_JET
3691  A0 03     VB_SLOT           LDY #$03                  ; a free missile slot (MISSILE_X = 0)? Y = 3..0
3693  B9 93 39  VB_SLOT_LOOP      LDA MISSILE_X,Y
3696  F0 06                       BEQ VB_SHOOT
3698  88                          DEY
3699  10 F8                       BPL VB_SLOT_LOOP
369B  4C DA 36                    JMP VB_JET
369E  AD 92 39  VB_SHOOT          LDA JET_X                 ; missile at JET_X+2, y = $B0; shot sound restarts at $B0
36A1  18                          CLC
36A2  69 02                       ADC #$02
36A4  99 93 39                    STA MISSILE_X,Y
36A7  A9 B0                       LDA #$b0
36A9  99 97 39                    STA MISSILE_Y,Y
36AC  8D 90 39                    STA SND_SHOT
36AF  98                          TYA
36B0  48                          PHA
36B1  B9 93 39                    LDA MISSILE_X,Y           ; reads the char under the new missile into HIT_CHAR ...
36B4  AA                          TAX
36B5  B9 97 39                    LDA MISSILE_Y,Y
36B8  A8                          TAY
36B9  20 36 39                    JSR CELL_ADDR
36BC  A0 00                       LDY #$00
36BE  B1 B6                       LDA (CELL),Y
36C0  8D 9C 39                    STA HIT_CHAR
36C3  68                          PLA
36C4  A8                          TAY
36C5  AD 9C 39                    LDA HIT_CHAR              ; ... but both branches go to VB_JET: the code below is unreachable
36C8  F0 10                       BEQ VB_JET
36CA  D0 0E                       BNE VB_JET
36CC  A9 00     VB_UNREACHED      LDA #$00
36CE  99 93 39                    STA MISSILE_X,Y
36D1  8D 90 39                    STA SND_SHOT
36D4  8D 04 D2                    STA AUDF3
36D7  8D 05 D2                    STA AUDC3
36DA  AD 92 39  VB_JET            LDA JET_X                 ; HPOSP0/1 = JET_X
36DD  8D 00 D0                    STA HPOSP0
36E0  8D 01 D0                    STA HPOSP1
36E3  A0 B0     VB_MISSILES_CLEAR LDY #$b0                  ; clear missile memory y = $29..$D8
36E5  A9 00                       LDA #$00
36E7  99 28 2B  VB_MC_LOOP        STA MISSILES+40,Y
36EA  88                          DEY
36EB  D0 FA                       BNE VB_MC_LOOP
36ED  A2 03     VB_MISSILES       LDX #$03                  ; each missile: HPOSM, y--, 2 pixels at y-1/y (mask by missile number); y < $30 -> slot free, y = $2F
36EF  BD 93 39  VB_MISSILE        LDA MISSILE_X,X
36F2  9D 04 D0                    STA HPOSM0,X
36F5  DE 97 39                    DEC MISSILE_Y,X
36F8  BD 97 39                    LDA MISSILE_Y,X
36FB  A8                          TAY
36FC  BD AE 39                    LDA MISSILE_MASKS,X
36FF  99 FF 2A                    STA MISSILES-1,Y
3702  99 00 2B                    STA MISSILES,Y
3705  C0 30                       CPY #$30
3707  B0 0A                       BCS VB_MISSILE_NEXT
3709  A9 00                       LDA #$00
370B  9D 93 39                    STA MISSILE_X,X
370E  A9 2F                       LDA #$2f
3710  9D 97 39                    STA MISSILE_Y,X
3713  CA        VB_MISSILE_NEXT   DEX
3714  10 D9                       BPL VB_MISSILE
3716  A2 03     VB_HITS           LDX #$03                  ; each active missile: the char under it (CELL_ADDR); HIT_CHARS[51..0] -> quadrant fix + HIT_HANDLERS
3718  8A        VH_MISSILE        TXA
3719  48                          PHA
371A  A9 00                       LDA #$00
371C  8D 9C 39                    STA HIT_CHAR
371F  BD 97 39                    LDA MISSILE_Y,X
3722  A8                          TAY
3723  BD 93 39                    LDA MISSILE_X,X
3726  F0 58                       BEQ VH_NEXT
3728  AA                          TAX
3729  20 36 39                    JSR CELL_ADDR
372C  A0 00                       LDY #$00
372E  B1 B6                       LDA (CELL),Y
3730  8D 9C 39                    STA HIT_CHAR
3733  F0 4B                       BEQ VH_NEXT
3735  A2 33     VH_FIND           LDX #$33
3737  DD FB 39  VH_FIND_LOOP      CMP HIT_CHARS,X
373A  F0 06                       BEQ VH_DISPATCH
373C  CA                          DEX
373D  10 F8                       BPL VH_FIND_LOOP
373F  4C 80 37                    JMP VH_NEXT
3742  8A        VH_DISPATCH       TXA                       ; X & 3 = quadrant of the 2x2 object; CELL -> its top-left
3743  29 03                       AND #$03
3745  0A                          ASL A
3746  A8                          TAY
3747  B9 2F 3A                    LDA QUADRANT_TAB,Y
374A  8D 63 37                    STA VH_JSR_QUADRANT+1
374D  B9 30 3A                    LDA QUADRANT_TAB+1,Y
3750  8D 64 37                    STA VH_JSR_QUADRANT+2
3753  8A                          TXA
3754  0A                          ASL A
3755  A8                          TAY
3756  B9 37 3A                    LDA HIT_HANDLERS,Y
3759  8D 66 37                    STA VH_JSR_HANDLER+1
375C  B9 38 3A                    LDA HIT_HANDLERS+1,Y
375F  8D 67 37                    STA VH_JSR_HANDLER+2
3762  20 31 38  VH_JSR_QUADRANT   JSR Q0
3765  20 CB 38  VH_JSR_HANDLER    JSR HIT_SOFT
3768  A9 00                       LDA #$00                  ; shot sound off, splash sound = 15, the missile is freed
376A  8D 90 39                    STA SND_SHOT
376D  8D 04 D2                    STA AUDF3
3770  8D 05 D2                    STA AUDC3
3773  A9 0F                       LDA #$0f
3775  8D 8F 39                    STA SND_SPLASH
3778  68                          PLA
3779  48                          PHA
377A  AA                          TAX
377B  A9 00                       LDA #$00
377D  9D 93 39                    STA MISSILE_X,X
3780  68        VH_NEXT           PLA
3781  AA                          TAX
3782  CA                          DEX
3783  30 03                       BMI VB_JET_HIT
3785  4C 18 37                    JMP VH_MISSILE
3788  AE 92 39  VB_JET_HIT        LDX JET_X                 ; the jet: the 2x2 chars at (JET_X, y = $B4): walls, shells, tanks kill
378B  A0 B4                       LDY #$b4
378D  20 36 39                    JSR CELL_ADDR
3790  A0 00                       LDY #$00
3792  20 1A 38                    JSR JET_PROBE
3795  C8                          INY
3796  20 1A 38                    JSR JET_PROBE
3799  A0 20                       LDY #$20
379B  20 1A 38                    JSR JET_PROBE
379E  C8                          INY
379F  20 1A 38                    JSR JET_PROBE
37A2  A5 14     VB_FUEL           LDA RTCLOK                ; every 32 frames FUEL -= 1 (BCD, 3 digits)
37A4  29 1F                       AND #$1f
37A6  D0 13                       BNE VB_FUEL_CHECK
37A8  F8                          SED
37A9  AD 9E 39                    LDA FUEL
37AC  38                          SEC
37AD  E9 01                       SBC #$01
37AF  8D 9E 39                    STA FUEL
37B2  AD 9F 39                    LDA FUEL_HI
37B5  E9 00                       SBC #$00
37B7  8D 9F 39                    STA FUEL_HI
37BA  D8                          CLD
37BB  AD 9F 39  VB_FUEL_CHECK     LDA FUEL_HI               ; FUEL below 0: DEATH, FUEL = 099
37BE  10 0F                       BPL VB_HUD_FUEL
37C0  A9 FF     VB_FUEL_OUT       LDA #$ff
37C2  8D 9D 39                    STA DEATH
37C5  A9 00                       LDA #$00
37C7  8D 9F 39                    STA FUEL_HI
37CA  A9 99                       LDA #$99
37CC  8D 9E 39                    STA FUEL
37CF  A2 05     VB_HUD_FUEL       LDX #$05                  ; HUD: fuel (3 digits at +5), jets (3 icons $6F at +16, $54 blank), score (6 digits at +26)
37D1  AD 9F 39                    LDA FUEL_HI
37D4  20 70 39                    JSR PUT_DIGIT
37D7  AD 9E 39                    LDA FUEL
37DA  20 67 39                    JSR PUT_BCD
37DD  AD A0 39  VB_HUD_JETS       LDA JETS
37E0  48                          PHA
37E1  EE A0 39                    INC JETS
37E4  A0 02                       LDY #$02
37E6  A9 6F     VB_HUD_JET        LDA #$6f
37E8  CE A0 39                    DEC JETS
37EB  10 02                       BPL L37EF
37ED  A9 54                       LDA #$54
37EF  99 53 3E  L37EF             STA HUD_JETS,Y
37F2  88                          DEY
37F3  10 F1                       BPL VB_HUD_JET
37F5  68                          PLA
37F6  8D A0 39                    STA JETS
37F9  A2 1A     VB_HUD_SCORE      LDX #$1a
37FB  AD A3 39                    LDA SCORE_2
37FE  20 67 39                    JSR PUT_BCD
3801  AD A2 39                    LDA SCORE_1
3804  20 67 39                    JSR PUT_BCD
3807  AD A1 39                    LDA SCORE
380A  20 67 39                    JSR PUT_BCD
380D  AD 84 02  VB_END            LDA STRIG0                ; TRIG_PREV = STRIG0; attract mode off
3810  8D 9B 39                    STA TRIG_PREV
3813  A9 00     VBI_IDLE          LDA #$00                  ; deferred VBI on the title screen and during the fade: attract mode off only
3815  85 4D                       STA ATRACT
3817  4C 62 E4                    JMP XITVBV
381A  B1 B6     JET_PROBE         LDA (CELL),Y              ; A = char at CELL+Y: >= $48 (tanks) or in DEADLY (walls, shells) -> DEATH
381C  C9 48                       CMP #$48
381E  B0 0B                       BCS JP_DIE
3820  A2 0D     JP_LOOP           LDX #$0d
3822  DD 9F 3A  L3822             CMP DEADLY,X
3825  F0 04                       BEQ JP_DIE
3827  CA                          DEX
3828  10 F8                       BPL L3822
382A  60                          RTS
382B  A9 FF     JP_DIE            LDA #$ff
382D  8D 9D 39                    STA DEATH
3830  60                          RTS
3831  60        Q0                RTS                       ; quadrant 0: nothing
3832  A5 B6     Q1                LDA CELL                  ; quadrant 1: CELL -= 1
3834  38                          SEC
3835  E9 01                       SBC #$01
3837  85 B6                       STA CELL
3839  A5 B7                       LDA CELL+1
383B  E9 00                       SBC #$00
383D  85 B7                       STA CELL+1
383F  60                          RTS
3840  A5 B6     Q2                LDA CELL                  ; quadrant 2: CELL -= 32
3842  38                          SEC
3843  E9 20                       SBC #$20
3845  85 B6                       STA CELL
3847  A5 B7                       LDA CELL+1
3849  E9 00                       SBC #$00
384B  85 B7                       STA CELL+1
384D  60                          RTS
384E  A5 B6     Q3                LDA CELL                  ; quadrant 3: CELL -= 33
3850  38                          SEC
3851  E9 21                       SBC #$21
3853  85 B6                       STA CELL
3855  A5 B7                       LDA CELL+1
3857  E9 00                       SBC #$00
3859  85 B7                       STA CELL+1
385B  60                          RTS
385C  A0 00     PUT_EXPLOSION     LDY #$00                  ; explosion frame 0 ($24 $25 / $26 $27) at CELL
385E  A9 24                       LDA #$24
3860  91 B6                       STA (CELL),Y
3862  C8                          INY
3863  A9 25                       LDA #$25
3865  91 B6                       STA (CELL),Y
3867  A0 20                       LDY #$20
3869  A9 26                       LDA #$26
386B  91 B6                       STA (CELL),Y
386D  C8                          INY
386E  A9 27                       LDA #$27
3870  91 B6                       STA (CELL),Y
3872  60                          RTS
3873  20 5C 38  HIT_FUEL          JSR PUT_EXPLOSION         ; fuel tile: explosion, +20 points, FUEL += 499 (BCD), capped at 999
3876  A9 20                       LDA #$20
3878  20 1C 39                    JSR ADD_SCORE
387B  F8                          SED
387C  AD 9E 39                    LDA FUEL
387F  18                          CLC
3880  69 99                       ADC #$99
3882  8D 9E 39                    STA FUEL
3885  AD 9F 39                    LDA FUEL_HI
3888  69 04                       ADC #$04
388A  8D 9F 39                    STA FUEL_HI
388D  D8                          CLD
388E  AD 9F 39                    LDA FUEL_HI
3891  C9 10                       CMP #$10
3893  B0 01                       BCS HF_CAP
3895  60                          RTS
3896  A9 09     HF_CAP            LDA #$09
3898  8D 9F 39                    STA FUEL_HI
389B  A9 99                       LDA #$99
389D  8D 9E 39                    STA FUEL
38A0  60                          RTS
38A1  20 5C 38  HIT_AMMO          JSR PUT_EXPLOSION         ; ammunition dump: explosion, +100 points
38A4  F8                          SED
38A5  AD A2 39                    LDA SCORE_1
38A8  18                          CLC
38A9  69 01                       ADC #$01
38AB  8D A2 39                    STA SCORE_1
38AE  AD A3 39                    LDA SCORE_2
38B1  69 00                       ADC #$00
38B3  8D A3 39                    STA SCORE_2
38B6  D8                          CLD
38B7  60                          RTS
38B8  20 5C 38  HIT_REPAIR        JSR PUT_EXPLOSION         ; repair: explosion, +30 points, a spare jet back (max 2)
38BB  A9 30                       LDA #$30
38BD  20 1C 39                    JSR ADD_SCORE
38C0  AD A0 39                    LDA JETS
38C3  C9 02                       CMP #$02
38C5  B0 03                       BCS L38CA
38C7  EE A0 39                    INC JETS
38CA  60        L38CA             RTS
38CB  20 5C 38  HIT_SOFT          JSR PUT_EXPLOSION         ; soft wall: explosion, +15 points
38CE  A9 15                       LDA #$15
38D0  4C 1C 39                    JMP ADD_SCORE
38D3  20 5C 38  HIT_TANK_R        JSR PUT_EXPLOSION         ; tank facing right: explosion over the 2x2, clear the third column, +55 points
38D6  A9 00                       LDA #$00
38D8  A0 02                       LDY #$02
38DA  91 B6                       STA (CELL),Y
38DC  A0 22                       LDY #$22
38DE  91 B6                       STA (CELL),Y
38E0  A9 55                       LDA #$55
38E2  4C 1C 39                    JMP ADD_SCORE
38E5  20 5C 38  HIT_TANK_L        JSR PUT_EXPLOSION         ; tank facing left (2x2 at $55): explosion, clear the blank column left of it, +55 points
38E8  A5 B6                       LDA CELL
38EA  38                          SEC
38EB  E9 01                       SBC #$01
38ED  85 B6                       STA CELL
38EF  A5 B7                       LDA CELL+1
38F1  E9 00                       SBC #$00
38F3  85 B7                       STA CELL+1
38F5  A9 00                       LDA #$00
38F7  A8                          TAY
38F8  91 B6                       STA (CELL),Y
38FA  A0 20                       LDY #$20
38FC  91 B6                       STA (CELL),Y
38FE  A9 55                       LDA #$55
3900  4C 1C 39                    JMP ADD_SCORE
3903  A0 40     HIT_HARD          LDY #$40                  ; hard wall: splash $1F in the row below the wall (hit from below) or in its bottom row, splash sound
3905  8A                          TXA
3906  29 02                       AND #$02
3908  D0 02                       BNE HH_COLUMN
390A  A0 20                       LDY #$20
390C  8A        HH_COLUMN         TXA
390D  29 01                       AND #$01
390F  F0 01                       BEQ L3912
3911  C8                          INY
3912  A9 1F     L3912             LDA #$1f
3914  91 B6                       STA (CELL),Y
3916  A9 0A                       LDA #$0a
3918  8D 8F 39                    STA SND_SPLASH
391B  60                          RTS
391C  F8        ADD_SCORE         SED                       ; SCORE += A (BCD), three bytes
391D  18                          CLC
391E  6D A1 39                    ADC SCORE
3921  8D A1 39                    STA SCORE
3924  A9 00                       LDA #$00
3926  6D A2 39                    ADC SCORE_1
3929  8D A2 39                    STA SCORE_1
392C  A9 00                       LDA #$00
392E  6D A3 39                    ADC SCORE_2
3931  8D A3 39                    STA SCORE_2
3934  D8                          CLD
3935  60                          RTS
3936  A9 00     CELL_ADDR         LDA #$00                  ; CELL = ROW_M1 + ((Y-41) & ~7) * 4 + (X-63) / 4: PM coordinates to the screen char
3938  85 B7                       STA CELL+1
393A  98                          TYA
393B  38                          SEC
393C  E9 29                       SBC #$29
393E  29 F8                       AND #$f8
3940  0A                          ASL A
3941  26 B7                       ROL CELL+1
3943  0A                          ASL A
3944  26 B7                       ROL CELL+1
3946  85 B6                       STA CELL
3948  8A                          TXA
3949  38                          SEC
394A  E9 3F                       SBC #$3f
394C  4A                          LSR A
394D  4A                          LSR A
394E  18                          CLC
394F  65 B6                       ADC CELL
3951  85 B6                       STA CELL
3953  A9 00                       LDA #$00
3955  65 B7                       ADC CELL+1
3957  85 B7                       STA CELL+1
3959  A5 B6                       LDA CELL
395B  18                          CLC
395C  69 63                       ADC #$63
395E  85 B6                       STA CELL
3960  A5 B7                       LDA CELL+1
3962  69 3B                       ADC #$3b
3964  85 B7                       STA CELL+1
3966  60                          RTS
3967  48        PUT_BCD           PHA                       ; two BCD digits at HUD+X (X += 2)
3968  4A                          LSR A
3969  4A                          LSR A
396A  4A                          LSR A
396B  4A                          LSR A
396C  20 70 39                    JSR PUT_DIGIT
396F  68                          PLA
3970  29 0F     PUT_DIGIT         AND #$0f                  ; one digit: screen code $10 + nibble
3972  09 10                       ORA #$10
3974  9D 43 3E                    STA HUD,X
3977  E8                          INX
3978  60                          RTS
3979  18        ADD_PTR           CLC                       ; zero-page pointer at Y += A
397A  79 00 00                    ADC $0000,Y
397D  99 00 00                    STA $0000,Y
3980  A9 00                       LDA #$00
3982  79 01 00                    ADC $0001,Y
3985  99 01 00                    STA $0001,Y
3988  60                          RTS
3989            VAR_UNUSED        .byte 00                       ;    ; never read
398A            VSCROL_CTR        .byte 07                       ; '  ; fine scroll 7..0
398B            ROW_TOGGLE        .byte 00                       ;    ; load a row every second shift
398C            PARITY            .byte 00                       ;    ; toggles every scan
398D            FLASH             .byte 00                       ;    ; frames left of the hit flash (50)
398E            SND_SHELL         .byte 00                       ;  
398F            SND_SPLASH        .byte 00                       ;  
3990            SND_SHOT          .byte 00                       ;  
3991            SND_DEATH         .byte 00                       ;  
3992            JET_X             .byte 00                       ;    ; jet x $40..$B9
3993            MISSILE_X         .byte 00 00 00 00              ;       ; x of missiles 0..3 (0 = free)
3997            MISSILE_Y         .byte 00 00 00 00              ;       ; y of missiles 0..3
399B            TRIG_PREV         .byte 00                       ;  
399C            HIT_CHAR          .byte 00                       ;  
399D            DEATH             .byte 00                       ;  
399E            FUEL              .byte 09                       ; )  ; fuel: BCD, low byte first
399F            FUEL_HI           .byte 00                       ;  
39A0            JETS              .byte 02                       ; "  ; spare jets 0..2
39A1            SCORE             .byte 00                       ;    ; score: BCD, low byte first
39A2            SCORE_1           .byte 00                       ;  
39A3            SCORE_2           .byte 00                       ;  
39A4            PAUSED            .byte 00                       ;  
39A5            COLOURS           .byte 04 08 06 0A 72 36 3C 1E  ; $(&*rV\>  ; PCOLR0-3, COLOR0-4
39AD                              .byte 00                       ;  
39AE            MISSILE_MASKS     .byte 01 04 10 40              ; !$0.  ; missile 0..3 pixel masks
39B2            JET_SHAPE0        .byte 10 10 38 38 10 10 BA BA  ; 00XX00..  ; player 0 shape
39BA                              .byte 38 7C 54 54 54           ; X|...
39BF            JET_SHAPE1        .byte 10 38 10 00 28 28 00 92  ; 0X0 HH .  ; player 1 shape
39C7                              .byte 10 92 BA BA              ; 0...
39CB            TILE_CHARS        .byte BA 23 22 25 24 21 3C 3E  ; .CBEDA\^  ; [0] unused, then # " % $ ! < >
39D3            TILE_TL           .byte 00 01 05 09 0D 11 54 48  ;  !%)-1..  ; top-left char per tile
39DB            TILE_TR           .byte 00 02 06 0A 0E 12 55 49  ;  "&*.2..  ; top-right
39E3            TILE_BL           .byte 00 03 07 0B 0F 13 74 68  ;  #'+/3th  ; bottom-left
39EB            TILE_BR           .byte 00 04 08 0C 10 14 75 69  ;  $(,04ui  ; bottom-right
39F3            EXPL_FRAMES       .byte 24 28 2C 30 34 38 3C 00  ; DHLPTX\   ; explosion frame bases, then 0
39FB            HIT_CHARS         .byte 05 06 07 08 09 0A 0B 0C  ; %&'()*+,  ; 52 chars a shot can hit: soft wall, fuel, ammo, repair, right tank x4 phases, left tank x4, hard wall
3A03                              .byte 0D 0E 0F 10 11 12 13 14  ; -./01234
3A0B                              .byte 48 49 68 69 4B 4C 6B 6C  ; ..hi..kl
3A13                              .byte 4E 4F 6E 6F 51 52 71 72  ; ..no..qr
3A1B                              .byte 55 56 75 76 58 59 78 79  ; ..uv..xy
3A23                              .byte 5B 5C 7B 7C 5E 5F 7E 7F  ; ..{|..~.
3A2B                              .byte 01 02 03 04              ; !"#$
3A2F            QUADRANT_TAB      .byte 31                       ; Q  ; quadrant fix routines
3A30            QUADRANT_TAB+1    .byte 38 32 38 40 38 4E 38     ; XRX.X.X
3A37            HIT_HANDLERS      .byte CB                       ; .  ; HIT handler per HIT_CHARS entry
3A38            HIT_HANDLERS+1    .byte 38 CB 38 CB 38 CB 38 73  ; X.X.X.Xs
3A40                              .byte 38 73 38 73 38 73 38 A1  ; XsXsXsX.
3A48                              .byte 38 A1 38 A1 38 A1 38 B8  ; X.X.X.X.
3A50                              .byte 38 B8 38 B8 38 B8 38 D3  ; X.X.X.X.
3A58                              .byte 38 D3 38 D3 38 D3 38 D3  ; X.X.X.X.
3A60                              .byte 38 D3 38 D3 38 D3 38 D3  ; X.X.X.X.
3A68                              .byte 38 D3 38 D3 38 D3 38 D3  ; X.X.X.X.
3A70                              .byte 38 D3 38 D3 38 D3 38 E5  ; X.X.X.X.
3A78                              .byte 38 E5 38 E5 38 E5 38 E5  ; X.X.X.X.
3A80                              .byte 38 E5 38 E5 38 E5 38 E5  ; X.X.X.X.
3A88                              .byte 38 E5 38 E5 38 E5 38 E5  ; X.X.X.X.
3A90                              .byte 38 E5 38 E5 38 E5 38 03  ; X.X.X.X#
3A98                              .byte 39 03 39 03 39 03 39     ; Y#Y#Y#Y
3A9F            DEADLY            .byte 01 02 03 04 05 06 07 08  ; !"#$%&'(  ; chars that kill the jet besides tanks: walls and shells
3AA7                              .byte 15 17 19 1A 1B           ; 579:;
3AAC            SCAN_CHARS        .byte 1C 48 4B 4E 51 54 57 5A  ; <.......  ; [0] never matched; tanks, shell frames, splash frames, explosion frames
3AB4                              .byte 5D 7A 6E 15 17 19 1B 1D  ; .zn579;=
3ABC                              .byte 1F 20 21 22 23 24 28 2C  ; ?@ABCDHL
3AC4                              .byte 30 34 38 3C              ; PTX\
3AC8            SCAN_HANDLERS     .byte 39                       ; Y  ; SCAN handler per SCAN_CHARS entry
3AC9            SCAN_HANDLERS+1   .byte 35 FC 33 FC 33 FC 33 FC  ; U.S.S.S.
3AD1                              .byte 33 35 34 35 34 35 34 35  ; SUTUTUTU
3AD9                              .byte 34 7B 34 7B 34 A3 34 A3  ; T{T{T.T.
3AE1                              .byte 34 A3 34 A3 34 A3 34 E2  ; T.T.T.T.
3AE9                              .byte 34 E2 34 E2 34 E2 34 E2  ; T.T.T.T.
3AF1                              .byte 34 F2 34 F2 34 F2 34 F2  ; T.T.T.T.
3AF9                              .byte 34 F2 34 F2 34 F2 34     ; T.T.T.T
3B00            DL_GAME           .byte 70 70 70 70 70 64 83 3B  ; pppppd.[  ; game display list: 40 blank lines, 20 x ANTIC 4 with VSCROL from ROW_0, DLI on row 18, blank+DLI, ANTIC 2 HUD
3B08                              .byte 24 24 24 24 24 24 24 24  ; DDDDDDDD
3B10                              .byte 24 24 24 24 24 24 24 24  ; DDDDDDDD
3B18                              .byte 24 A4 24 80 42 43 3E 41  ; D.D...^.
3B20                              .byte 00 3B                    ;  [
3B22            DL_TITLE          .byte 70 70 70 70 70 70 70 70  ; pppppppp  ; title display list: 64 blank lines, 6 x ANTIC 2 from TITLE_TEXT, 88 blank lines, ANTIC 2 HUD
3B2A                              .byte 42 63 3E 02 02 02 02 02  ; .c^"""""
3B32                              .byte 70 70 70 70 70 70 70 70  ; pppppppp
3B3A                              .byte 70 70 70 42 43 3E 41 22  ; ppp..^.B
3B42            SCREEN-1          .byte 3B                       ; [

; ===== segment $3E43-$3F24: status line (32 bytes), title screen (6 rows of 32,
;       ANTIC 2 screen codes with bit 7 = inverse; rows 0-3 draw the logo with control-graphics),
;       BOARD_END (2 bytes, rewritten by INIT)
3E43  HUD               .byte 26 75 65 6C 1A 10 10 10 00 24 61 6D 61 67 65 1A 54 54 54 00 33 63 6F 72 65 1A 10 10 10 10 10 10
                         ; "Fuel:000 Damage:... Score:000000"
3E63  TITLE_TEXT        .byte C9 CF C9 CF 4B 80 00 80 4C CF C9 D5 CF 00 00 00 00 D9 80 C9 80 80 D9 80 80 80 59 80 80 80 80 80
                         ; ".....   .....    . .  .   .     "
3E83                    .byte 00 D9 59 00 00 80 55 80 00 D9 CB 55 00 00 00 00 00 4B D5 4C 80 80 D9 80 CB 55 00 4C D9 80 59 4B
                         ; " ..   .  ...     ...  . .. .. .."
3EA3                    .byte 00 D9 59 00 00 80 00 80 00 D9 59 00 00 00 00 00 00 D9 80 59 80 80 D9 80 C9 D5 00 00 D9 80 59 00
                         ; " ..      ..      . .  . ..  . . "
3EC3                    .byte 00 CC CB 00 49 80 00 80 4F CC CB 55 CC 00 00 00 00 4B 80 80 80 C9 D9 80 80 80 59 00 D9 80 59 00
                         ; " .. .   .....    .   ..   . . . "
3EE3                    .byte 00 37 72 69 74 74 65 6E 00 62 79 1A 00 24 61 72 69 75 73 7A 00 3A 6F 6C 6E 61 00 11 19 19 12 00
                         ; " Written by: Dariusz Zolna 1992 "
3F03                    .byte 00 00 00 00 08 63 09 00 11 19 19 12 00 24 65 00 2A 65 74 00 73 6F 66 74 74 65 61 6D 00 00 00 00
                         ; "    (c) 1992 De Jet softteam    "
3F23  BOARD_END         .byte 15 3F
                         ; "5_"
