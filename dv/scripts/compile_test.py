#!/usr/bin/env python3
"""编译 RISC-V 汇编测试为 .hex 格式"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

PICORV32_ROOT = Path(__file__).parent.parent.parent
LINKER_SCRIPT = PICORV32_ROOT / "dv/cfg/sections.lds"
MAKEHEX = PICORV32_ROOT / "firmware/makehex.py"
BOOT_ASM = PICORV32_ROOT / "dv/cfg/picorv32_boot.S"
CUSTOM_OPS = PICORV32_ROOT / "firmware/custom_ops.S"
TOOLCHAIN_PREFIX = "riscv64-unknown-elf-"

def run_cmd(cmd, cwd=None):
    """执行命令并检查返回值"""
    print(f"[CMD] {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] {result.stderr}")
        sys.exit(1)
    return result.stdout

def compile_test(asm_file, output_dir):
    """编译 .S → .elf → .bin → .hex

    链接顺序: picorv32_boot.o (位于 .text.boot) + test.o (.text)
    确保 boot + trap handler 在 0x80000000 起始。
    """
    asm_file = Path(asm_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 复制 user_define.h, user_init.s, custom_ops.S 到汇编文件目录
    cfg_dir = PICORV32_ROOT / "dv/cfg"
    asm_dir = asm_file.parent
    shutil.copy(cfg_dir / "user_define.h", asm_dir / "user_define.h")
    shutil.copy(cfg_dir / "user_init.s", asm_dir / "user_init.s")
    shutil.copy(CUSTOM_OPS, asm_dir / "custom_ops.S")

    elf_file = output_dir / "test.elf"
    bin_file = output_dir / "test.bin"
    hex_file = output_dir / "test.hex"
    dmp_file = output_dir / "test.dmp"
    boot_obj = output_dir / "picorv32_boot.o"

    march = "rv32imc_zicsr_zifencei"

    # 1. 编译 boot 代码为 .o（需要 custom_ops.S 在 include path）
    run_cmd(f"{TOOLCHAIN_PREFIX}gcc -march={march} -mabi=ilp32 "
            f"-ffreestanding -nostdlib -c "
            f"-I{asm_dir} "
            f"-Wa,-I,{asm_dir} "
            f"-o {boot_obj} {BOOT_ASM}")

    # 2. 编译并链接 boot.o + test.S → .elf
    #    boot.o 放在最前面确保 .text.boot 在 0x80000000
    run_cmd(f"{TOOLCHAIN_PREFIX}gcc -march={march} -mabi=ilp32 "
            f"-ffreestanding -nostdlib "
            f"-I{asm_dir} "
            f"-Wa,-I,{asm_dir} "
            f"-Wl,-Bstatic,-T,{LINKER_SCRIPT} "
            f"-o {elf_file} {boot_obj} {asm_file}")

    # 3. 生成 .bin
    run_cmd(f"{TOOLCHAIN_PREFIX}objcopy -O binary {elf_file} {bin_file}")

    # 3.5. 填充到 4 字节对齐
    with open(bin_file, 'ab') as f:
        size = bin_file.stat().st_size
        padding = (4 - size % 4) % 4
        if padding:
            f.write(b'\x00' * padding)

    # 4. 转换为 .hex (256KB = 65536 words)
    hex_data = run_cmd(f"python3 {MAKEHEX} {bin_file} 65536")
    hex_file.write_text(hex_data)

    # 5. 生成反汇编 .dmp (用于调试)
    dmp_data = run_cmd(f"{TOOLCHAIN_PREFIX}objdump -d {elf_file}")
    dmp_file.write_text(dmp_data)

    # 6. 提取 tohost 符号地址（用于 testbench 终止检测）
    tohost_addr = None
    nm_output = run_cmd(f"{TOOLCHAIN_PREFIX}nm {elf_file}")
    for line in nm_output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[2] == "tohost":
            tohost_addr = parts[0]
            break
    if tohost_addr:
        tohost_file = output_dir / "tohost_addr.txt"
        tohost_file.write_text(tohost_addr)
        print(f"[INFO] tohost address: 0x{tohost_addr}")

    print(f"[SUCCESS] Generated: {hex_file}")
    return hex_file

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <asm_file> <output_dir>")
        sys.exit(1)

    compile_test(sys.argv[1], sys.argv[2])
