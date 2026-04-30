#!/usr/bin/env python3
"""修复 dayahead_core.py 中的编码乱码问题

将文件中被损坏的中文进度消息替换为正确文本。
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TARGET_FILE = BASE_DIR / "dayahead_core.py"

# 备份原文件
backup = BASE_DIR / "dayahead_core.py.bak"
backup.write_bytes(TARGET_FILE.read_bytes())
print(f"已备份原文件至: {backup}")

# 读取文件
content = TARGET_FILE.read_text(encoding="utf-8")

# 定义需要替换的乱码 -> 正确文本映射
# key: 乱码行中的唯一标识 (不包含乱码部分)
# value: 完整的新行
fixes = {}

# 收集所有包含连续 4+ 个 "?" 的行
lines = content.split("\n")
fix_count = 0

for i, line in enumerate(lines):
    # 匹配 emit_progress 行中包含连续问号的
    if "emit_progress" in line and re.search(r"\?{4,}", line):
        original = line

        # 基于上下文确定正确的文本
        if "lag_96" in line:
            line = line.replace(
                re.findall(r'"([^"]*\?{4,}[^"]*)"', line)[0],
                "正在构建 lag_96 特征"
            )
        elif "progress_label" in line and "????????" in line:
            line = line.replace(
                re.findall(r'"([^"]*\?{4,}[^"]*)"', line)[0],
                "正在读取数据"
            )
        elif "filter_date_range" in lines[max(0, i-1)]:
            # 这行上面有 filter_date_range
            continue  # 已被上面的替换处理
        elif i > 0 and "相似法" in lines[i-1]:
            # 相似法后面的乱码
            old_str = re.findall(r'"([^"]*\?{4,}[^"]*)"', line)
            if old_str:
                line = line.replace(old_str[0], "相似法特征构建完成")
        else:
            # 剩余的乱码行，按位置判断
            old_str = re.findall(r'"([^"]*\?{4,}[^"]*)"', line)
            if not old_str:
                continue
            old = old_str[0]

            # 根据乱码长度和上下文推断
            ctx_before = lines[i-1].strip() if i > 0 else ""
            ctx_after = lines[i+1].strip() if i < len(lines) - 1 else ""

            if "progress_label" in line:
                line = line.replace(old, "正在加载历史数据")
            elif "load_forecast_generic" in ctx_after or "load_forecast" in ctx_after:
                line = line.replace(old, "历史数据加载完成，正在加载预测文件")
            elif "load_models" in ctx_after:
                line = line.replace(old, "正在加载当前默认模型")
            elif "export_prediction" in ctx_after or "write_prediction" in ctx_after:
                line = line.replace(old, "正在导出预测结果")
            elif "template_updated" in ctx_after or "forecast_date" in ctx_after:
                line = line.replace(old, "预测任务完成")
            elif "strategy_label" in line or "strategy" in line.lower():
                line = re.sub(
                    r'f"(\?+)\s*\{(.+?)\}\s*/\s*(\?+)\{(.+?)\}"',
                    r'f"正在预测 \2 / 时段\4"',
                    line
                )
                if line == original:  # 如果正则没匹配上
                    line = re.sub(r'f"(\?+)\s*\{', 'f"正在执行 {\}', line)
            elif "strategy_index" in line:
                line = re.sub(r'f"(\?+)\s*\{', 'f"正在对比策略 {', line)
            elif "selected_result" in line:
                line = re.sub(r'f"(\?+)\s*\{', 'f"预测完成，已选择策略 {', line)
                line = re.sub(r'\?\?$', '"', line.rstrip('?"')) + '"'
            elif re.match(r'^\s*emit_progress\(.*\b5\b', line):
                line = line.replace(old, "开始加载预测所需数据")
            elif re.match(r'^\s*emit_progress\(.*\b45\b', line):
                line = line.replace(old, "正在加载当前默认模型")
            elif re.match(r'^\s*emit_progress\(.*\b50\b', line):
                line = line.replace(old, "正在执行预测策略")
            elif re.match(r'^\s*emit_progress\(.*\b92\b', line):
                line = line.replace(old, "正在导出预测结果")
            elif re.match(r'^\s*emit_progress\(.*\b20\b', line):
                line = line.replace(old, "历史数据加载完成，正在加载预测文件")
            elif re.match(r'^\s*emit_progress\(.*\b100\b', line):
                line = line.replace(old, "预测任务完成")

        if line != original:
            lines[i] = line
            fix_count += 1
            print(f"  已修复行 {i+1}: {original.strip()[:60]} -> {line.strip()[:60]}")

# 修复错误消息
for i, line in enumerate(lines):
    if "正在加载历史数据文件正在加载历史数据文件" in line:
        lines[i] = line.replace(
            "正在加载历史数据文件正在加载历史数据文件?",
            "数据加载后经清洗为空，请检查历史数据文件是否包含有效数据。"
        )
        fix_count += 1
        print(f"  已修复行 {i+1}: 错误提示信息")

# 写回文件
fixed_content = "\n".join(lines)
TARGET_FILE.write_text(fixed_content, encoding="utf-8")

print(f"\n修复完成！共修复 {fix_count} 处乱码。")
print(f"原文件备份在: {backup}")
