# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PicoRV32 is a small, high-frequency RISC-V RV32IMC CPU core with two verification environments:
- **Root-level tests**: Icarus Verilog / Verilator simulations with hand-written firmware
- **dv/ RISCV-DV flow**: VCS-based random instruction verification with Spike ISS comparison

## Build Commands

### Root-level simulation (Icarus Verilog)
```bash
make test              # Standard testbench with firmware
make test_ez           # Self-contained testbench (no external firmware)
make test_wb           # Wishbone interface testbench
make test_axi          # AXI4-Lite interface test
make test_verilator    # Verilator C++ simulation
make test_vcd          # Standard test + VCD waveform dump
```

### Formal verification
```bash
make check-yices       # yosys-smtbmc bounded model checking
```

### RISCV-DV random instruction verification (VCS)
```bash
# From repo root (delegates to dv/Makefile):
make riscv_dv_compile                              # Compile VCS testbench once
make riscv_dv_test TEST=<test_name>                # Run single test (all stages)
make riscv_dv_test TEST=<test_name> SEED=<num>     # Reproducible run
make riscv_dv_merge_cov                            # Merge all test coverage DBs
make riscv_dv_cov_report                           # Generate HTML coverage report
make riscv_dv_clean                                # Remove dv/out/

# Or equivalently from dv/:
cd dv && make compile_vcs
cd dv && make run_test TEST=<test_name>
```

**Available test names** (defined in `dv/cfg/testlist.yaml`):
- `riscv_arithmetic_basic_test` — ADD/SUB/AND/OR/XOR/SLT/SLTU (strict mode)
- `riscv_shift_test` — SLL/SRL/SRA (strict mode)
- `riscv_load_store_test` — Load/store instructions (strict mode)
- `riscv_branch_test` — Branch instructions (strict mode)
- `riscv_jump_test` — JAL/JALR (self-check mode)
- `riscv_lui_auipc_test` — LUI/AUIPC (strict mode)
- `riscv_rand_instr_test` — Random RV32IMC mix (self-check mode)
- `riscv_mul_div_test` — MUL/MULH/MULHSU/MULHU (strict mode)
- `riscv_illegal_instr_test` — Illegal instruction recovery (self-check mode)

### Toolchain (if not yet installed)
```bash
make download-tools
make build-riscv32imc-tools   # Installs to /opt/riscv32imc/
```

## Architecture

### RTL
- **`picorv32.v`** — All CPU variants in one file: `picorv32` (native memory), `picorv32_axi` (AXI4-Lite wrapper), `picorv32_wb` (Wishbone wrapper), and two PCPI multiplier cores
- The core is configured entirely through Verilog `parameter`s (no ifdefs). Key ones: `ENABLE_MUL`, `ENABLE_DIV`, `ENABLE_IRQ`, `COMPRESSED_ISA`, `ENABLE_REGS_DUALPORT`
- RVFI (RISC-V Formal Interface) is emitted when `RISCV_FORMAL` is defined

### RISCV-DV Verification Flow

The flow in `dv/scripts/run_riscv_dv.py` has five sequential stages per test:

1. **generate** — RISCV-DV framework generates random RISC-V assembly (`dv/riscv-dv/run.py`)
2. **compile** — `compile_test.py` links `picorv32_boot.S` + generated ASM → ELF/HEX
3. **spike** — `spike_runner.py` runs Spike ISS to produce reference trace
4. **simulate** — VCS runs `dv/tb/testbench_vcs.sv` with RVFI tracing
5. **compare** — `compare_trace.py` compares Spike vs RTL traces

**Two comparison modes:**
- **strict**: Instruction-by-instruction PC + register-write comparison against Spike
- **self-check**: RTL-only sanity (instruction count, termination, no dead loops) — used when Spike diverges on control flow

### PicoRV32-specific DV adaptations
- **`dv/cfg/picorv32_boot.S`** — Custom boot/IRQ handler: unmasks IRQ[1] (illegal instr) and IRQ[2] (bus error); handler recovers by clearing compressed bit and stepping over the faulting instruction
- **`dv/cfg/user_define.h`** — Macro replacements: `ecall → j write_tohost`, `mret → nop`
- **`dv/cfg/riscv_core_setting.sv`** — Generator constraints: disables DIV/DIVU/REM/REMU (avoid divide-by-zero), CSR/ECALL/EBREAK/MRET, unaligned accesses, WFI/FENCE
- **`dv/cfg/testlist.yaml`** — Each test entry specifies `num_of_tests`, `num_of_sub_program`, `instr_cnt`, `compare_mode`, and optional instruction-category overrides

### Coverage
VCS collects `line+cond+fsm+tgl+branch` coverage. Per-test databases land in `dv/out/picorv32/<test>/coverage/`. `merge_cov` uses `urg` to merge into `dv/out/merged_coverage/` with an HTML dashboard at `dashboard.html`.

### Output layout
```
dv/out/
  build/simv               # VCS compiled executable
  build/coverage.vdb       # Incremental coverage DB
  picorv32/<test_name>/
    gen/                   # RISCV-DV generated assembly
    bin/                   # ELF, hex, disassembly
    spike.log              # Spike reference trace
    rtl.log                # VCS RVFI trace
    coverage/report/       # Per-test HTML coverage
  merged_coverage/         # Merged across all tests
```

## Tool Prerequisites
- **Synopsys VCS** — required for the `dv/` flow
- **Spike ISS** — RISC-V reference model (`spike --isa=rv32imc_zicsr`)
- **RISC-V GCC** — `riscv64-unknown-elf-gcc` with `march=rv32imc_zicsr_zifencei`
- **Python 3.6+** with PyYAML — test orchestration
- **Icarus Verilog + vvp** — root-level tests
- **Verilator** — `make test_verilator`
- **Yosys + yosys-smtbmc** — formal verification
