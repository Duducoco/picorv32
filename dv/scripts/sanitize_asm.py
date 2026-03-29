#!/usr/bin/env python3
"""可选的 JALR 地址约束后处理脚本

扫描 RISCV-DV 生成的 .S 文件，在每个 JALR 指令前插入地址约束指令，
确保跳转目标在有效内存范围 [0x80000000, 0x8003FFFF] 内。

注意：此脚本会降低随机性，优先依赖 trap handler 处理越界跳转。
仅在需要减少异常频率以提高有效指令覆盖率时使用。

用法: sanitize_asm.py <input.S> <output.S>
"""

import sys
import re
from pathlib import Path

# 有效内存范围
MEM_BASE = 0x80000000
MEM_END  = 0x80040000  # 256KB

# JALR 指令匹配模式: jalr rd, offset(rs1) 或 jalr rs1
JALR_PATTERN = re.compile(
    r'^(\s+)(jalr)\s+'
    r'(?:(\w+)\s*,\s*)?'       # optional rd
    r'(-?\d+)?\s*'             # optional offset
    r'\(?(\w+)\)?'             # rs1 (可能被括号包裹)
    r'\s*(#.*)?$',             # optional comment
    re.IGNORECASE
)

# 简化的 JALR 模式: jalr rs1
JALR_SIMPLE_PATTERN = re.compile(
    r'^(\s+)(jalr)\s+(\w+)\s*(#.*)?$',
    re.IGNORECASE
)

# 寄存器名映射（排除 x0/zero）
TEMP_REGS = ['t0', 't1', 't2', 't3', 't4', 't5', 't6']

def find_temp_reg(used_regs):
    """查找未使用的临时寄存器"""
    for reg in TEMP_REGS:
        if reg not in used_regs:
            return reg
    return None

def sanitize_jalr(line, line_num):
    """处理单行 JALR 指令，返回替换后的行列表"""
    # 尝试匹配 JALR 指令
    m = JALR_PATTERN.match(line)
    if not m:
        m = JALR_SIMPLE_PATTERN.match(line)
        if not m:
            return [line]
        indent = m.group(1)
        rs1 = m.group(3)
        comment = m.group(4) or ''
        rd = 'ra'
        offset = '0'
    else:
        indent = m.group(1)
        rd = m.group(3) or 'ra'
        offset = m.group(4) or '0'
        rs1 = m.group(5)
        comment = m.group(6) or ''

    # 不处理跳转到 x0 的情况（不会越界）
    if rs1 in ('x0', 'zero'):
        return [line]

    # 查找可用的临时寄存器（排除 rd 和 rs1）
    used = {rd, rs1}
    tmp = find_temp_reg(used)
    if not tmp:
        # 无可用临时寄存器，跳过约束
        return [line]

    # 生成地址约束代码
    result = []
    result.append(f"{indent}# [sanitize] Constrain JALR target at line {line_num}")
    result.append(f"{indent}lui {tmp}, %hi({MEM_BASE})")
    result.append(f"{indent}or {rs1}, {rs1}, {tmp}")
    result.append(f"{indent}lui {tmp}, %hi({MEM_END})")
    label = f".Ljalr_ok_{line_num}"
    result.append(f"{indent}bltu {rs1}, {tmp}, {label}")
    result.append(f"{indent}lui {rs1}, %hi({MEM_BASE})")
    result.append(f"{label}:")
    result.append(line)
    return result

def sanitize_file(input_path, output_path):
    """处理整个 .S 文件"""
    input_path = Path(input_path)
    output_path = Path(output_path)

    with open(input_path) as f:
        lines = f.readlines()

    output_lines = []
    jalr_count = 0
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip('\n')
        # 跳过注释行和空行
        if stripped.strip().startswith('#') or stripped.strip().startswith('//') or not stripped.strip():
            output_lines.append(line)
            continue

        # 检查是否是 JALR 指令
        if re.search(r'\bjalr\b', stripped, re.IGNORECASE):
            sanitized = sanitize_jalr(stripped, i)
            if len(sanitized) > 1:
                jalr_count += 1
            for s in sanitized:
                output_lines.append(s + '\n')
        else:
            output_lines.append(line)

    with open(output_path, 'w') as f:
        f.writelines(output_lines)

    print(f"[INFO] Sanitized {jalr_count} JALR instructions in {input_path.name}")
    return jalr_count

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.S> <output.S>")
        sys.exit(1)

    sanitize_file(sys.argv[1], sys.argv[2])
