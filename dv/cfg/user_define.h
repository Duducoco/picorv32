# PicoRV32 user defines for RISCV-DV
# Override ecall to jump to write_tohost (RISCV-DV standard HTIF exit mechanism)
# Both Spike (via HTIF tohost monitoring) and RTL testbench (via loop detection)
# use this to terminate simulation.
.macro ecall
j write_tohost
.endm
# Override mret to be a nop (PicoRV32 doesn't support standard mret)
.macro mret
nop
.endm
