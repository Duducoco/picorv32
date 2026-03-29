// PicoRV32 RISCV-DV generator configuration
// Matches testbench: ENABLE_MUL=1, ENABLE_DIV=1, COMPRESSED_ISA=1
// No standard CSR/trap support (custom IRQ mechanism)

// XLEN
parameter int XLEN = 32;

// No address translation
parameter satp_mode_t SATP_MODE = BARE;

// Only Machine mode
privileged_mode_t supported_privileged_mode[] = {MACHINE_MODE};

// Unsupported instructions - PicoRV32 has no standard CSR/trap/fence support
riscv_instr_name_t unsupported_instr[] = {
    CSRRW, CSRRS, CSRRC, CSRRWI, CSRRSI, CSRRCI,
    ECALL, EBREAK, MRET, SRET, URET, DRET,
    WFI, FENCE, FENCE_I
};

// ISA: RV32IMC
riscv_instr_group_t supported_isa[$] = {RV32I, RV32M, RV32C};

// No vectored interrupt support (PicoRV32 uses fixed PROGADDR_IRQ)
mtvec_mode_t supported_interrupt_mode[$] = {DIRECT};

int max_interrupt_vector_num = 0;

// No PMP
bit support_pmp = 0;
bit support_epmp = 0;

// No debug mode
bit support_debug_mode = 0;

// No user mode trap delegation
bit support_umode_trap = 0;

// No sfence
bit support_sfence = 0;

// PicoRV32 with CATCH_MISALIGN=1 traps on unaligned access
// (our handler recovers, but avoid generating them for cleaner tests)
bit support_unaligned_load_store = 1'b0;

// GPR setting
parameter int NUM_FLOAT_GPR = 32;
parameter int NUM_GPR = 32;
parameter int NUM_VEC_GPR = 32;

// No vector extension
parameter int VECTOR_EXTENSION_ENABLE = 0;
parameter int VLEN = 512;
parameter int ELEN = 32;
parameter int SELEN = 8;
parameter int VELEN = int'($ln(ELEN)/$ln(2)) - 3;
parameter int MAX_LMUL = 8;

// Single hart
parameter int NUM_HARTS = 1;

// PicoRV32 only supports cycle/instret counters (read-only, no standard CSRs)
`ifdef DSIM
privileged_reg_t implemented_csr[] = {
`else
const privileged_reg_t implemented_csr[] = {
`endif
    MHARTID
};

// No custom CSRs
bit [11:0] custom_csr[] = {
};

// No standard interrupt/exception handling
`ifdef DSIM
interrupt_cause_t implemented_interrupt[] = {
`else
const interrupt_cause_t implemented_interrupt[] = {
`endif
};

`ifdef DSIM
exception_cause_t implemented_exception[] = {
`else
const exception_cause_t implemented_exception[] = {
`endif
    ILLEGAL_INSTRUCTION,
    LOAD_ADDRESS_MISALIGNED
};
