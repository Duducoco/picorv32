#!/usr/bin/env python3
"""运行 Spike ISS 生成参考 trace

针对 PicoRV32 DV 环境的特殊处理:
- ELF 包含 picorv32 自定义指令的 boot 代码，Spike 无法执行
- 因此提取 'init' 标签地址，让 Spike 从该地址启动
- Spike 只执行 init 之后的用户代码
"""

import sys
import subprocess
import re
from pathlib import Path

PICORV32_ROOT = Path(__file__).parent.parent.parent
TOOLCHAIN_PREFIX = "riscv64-unknown-elf-"

def get_symbol_addr(elf_file, symbol):
    """从 ELF 中提取符号地址"""
    result = subprocess.run(
        f"{TOOLCHAIN_PREFIX}nm {elf_file}",
        shell=True, capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[2] == symbol:
            return int(parts[0], 16)
    return None

def run_spike(elf_file, output_log):
    """运行 Spike 并生成 trace log

    从 init 标签地址启动 Spike，跳过 picorv32 自定义 boot 代码。
    """
    elf_file = Path(elf_file)
    output_log = Path(output_log)
    output_log.parent.mkdir(parents=True, exist_ok=True)

    # 提取 init 标签地址（跳过 boot 和 CSR 初始化代码）
    init_addr = get_symbol_addr(elf_file, "init")
    if init_addr is None:
        print("[ERROR] Cannot find 'init' symbol in ELF")
        return None

    print(f"[INFO] Starting Spike at init=0x{init_addr:08x}")

    cmd = (f"spike --isa=rv32imc_zicsr "
           f"--pc=0x{init_addr:x} "
           f"--log-commits "
           f"-m0x80000000:0x40000 "
           f"-l {elf_file}")

    print(f"[CMD] {cmd}")

    try:
        result = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        print("[ERROR] Spike timed out after 60 seconds")
        return None

    # Spike -l 输出到 stderr，--log-commits 也输出到 stderr
    log_content = result.stderr if result.stderr else result.stdout

    if not log_content:
        print("[ERROR] Spike produced no output")
        if result.stdout:
            print(f"[DEBUG] stdout: {result.stdout[:500]}")
        return None

    output_log.write_text(log_content)
    line_count = len(log_content.splitlines())
    print(f"[SUCCESS] Spike trace: {output_log} ({line_count} lines)")
    return output_log

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <elf_file> <output_log>")
        sys.exit(1)

    result = run_spike(sys.argv[1], sys.argv[2])
    sys.exit(0 if result else 1)
