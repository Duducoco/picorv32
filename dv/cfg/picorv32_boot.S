// PicoRV32 Boot Code + Trap Handler for RISCV-DV
// Handles illegal instruction (irq[1]) and bus error (irq[2]) exceptions
// by resuming execution at the next instruction after the faulting one.
//
// q0 semantics (set by hardware on IRQ entry):
//   q0 = reg_next_pc | latched_compr
//   reg_next_pc = faulting_pc + (compressed ? 2 : 4)  (already past the fault)
//   bit 0 = compressed instruction marker
// Therefore: return address = q0 & ~1  (just clear the marker bit)

#include "custom_ops.S"

.section .text.boot
.global _boot

// Disable compressed instructions in boot section
// to ensure predictable sizing for IRQ handler alignment.
.option push
.option norvc

_boot:
    // Reset entry point at 0x80000000
    // Unmask irq[1] (illegal insn) and irq[2] (bus error)
    // maskirq: bit=1 means masked/disabled, bit=0 means enabled
    // 0xFFFFFFF8 = ~0x7 -> enable bits 0,1,2; mask all others
    addi x1, x0, -8            // x1 = 0xFFFFFFF8
    picorv32_maskirq_insn(x0, x1)
    j boot_cont                 // jump past IRQ handler

// IRQ entry point must be exactly at offset 0x10 (PROGADDR_IRQ = PROGADDR_RESET + 0x10)
.org 0x10
irq_vec:
    // Save x1 to q2 (only need one temp register now)
    picorv32_setq_insn(q2, x1)

    // Read return address from q0
    // q0 = (faulting_pc + instr_size) | compressed_bit
    // Clear bit 0 to get the actual next PC
    picorv32_getq_insn(x1, q0)
    andi x1, x1, -2            // x1 = next instruction address

    // Write corrected return address back to q0
    picorv32_setq_insn(q0, x1)

    // Restore x1
    picorv32_getq_insn(x1, q2)

    // Return from interrupt (jumps to address in q0)
    picorv32_retirq_insn()

boot_cont:
    // Set x5 (t0) = _start address to match Spike boot ROM behavior.
    // Spike's default boot ROM sets t0 = reset_vector (--pc value) before jumping.
    // RISCV-DV's init code skips x5 initialization (convention: set by boot env).
    // spike_runner.py uses --pc=_start, so Spike's t0 = _start address.
    la x5, _start
    j _start                    // jump to RISCV-DV generated program entry

.option pop
