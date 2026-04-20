# Directed test: exercise RDCYCLE / RDCYCLEH / RDINSTR / RDINSTRH counter paths.
# PicoRV32 uses fixed encodings for these CSR reads (ENABLE_COUNTERS=1, ENABLE_COUNTERS64=1).
# Loops 30 times so the counters return visibly different values each read.

.include "user_define.h"
.globl _start
.section .text
_start:
    la sp, _stack_top

    li t1, 30
_counter_loop:
    .word 0xC0002573    # rdcycle   a0  (csrrs a0, cycle, x0)
    .word 0xC8002573    # rdcycleh  a0  (csrrs a0, cycleh, x0)
    .word 0xC0202573    # rdinstret a0  (csrrs a0, instret, x0)
    .word 0xC8202573    # rdinstreth a0 (csrrs a0, instreth, x0)
    addi t1, t1, -1
    bnez t1, _counter_loop

    # Terminate — ecall macro (from user_define.h) jumps to write_tohost
    ecall

write_tohost:
    li a0, 1
    la t0, tohost
    sw a0, 0(t0)
_end_loop:
    j _end_loop

.section .data
.globl tohost
.align 2
tohost: .word 0

.section .bss
.align 4
.space 256
_stack_top:
