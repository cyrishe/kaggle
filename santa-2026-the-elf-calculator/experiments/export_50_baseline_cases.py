#!/usr/bin/env python3
"""Export a reproducible sample of complete programs with target hits marked."""
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

from first_solver import validate

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / 'external/hansen_0652a700/submission.csv'
DEFAULT_PUZZLES = ROOT / 'data/puzzles.csv'
DEFAULT_OUTPUT = ROOT / 'reports/baseline_random_50_cases.md'
SOURCE = ('https://github.com/Hansen0223/Santa_2026/blob/'
          '0652a700782bf452d35255b9b4993f547412cfcc/submission.csv')
csv.field_size_limit(1_000_000)


def replay(puzzle, program):
    validate(puzzle, program)
    starts = json.loads(puzzle['starting_values'])
    targets = set(json.loads(puzzle['targets']))
    values = starts + [None] * (int(puzzle['registers']) - len(starts))
    covered = targets.intersection(starts)
    rows = []
    for step, (op, left, right, dest) in enumerate(program, 1):
        a, b = values[left], values[right]
        if op == '+': value = a + b
        elif op == '-': value = a - b
        elif op == '*': value = a * b
        elif op == '/': value = a // b
        else: raise ValueError(f'Unknown operator {op}')
        marker = ''
        if value in targets:
            marker = '★ 首次命中' if value not in covered else '★ 再次出现'
            covered.add(value)
        rows.append((step, left, a, op, right, b, dest, value, marker))
        values[dest] = value
    if covered != targets:
        raise ValueError(f"Missing targets for {puzzle['id']}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--puzzles', type=Path, default=DEFAULT_PUZZLES)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--seed', type=int, default=20261124)
    parser.add_argument('--sample', type=int, default=50)
    args = parser.parse_args()
    with args.puzzles.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    puzzles = {row['id']: row for row in rows}
    if len(rows) != len(puzzles) or not 1 <= args.sample <= len(puzzles):
        parser.error('Duplicate puzzle IDs or invalid sample size')
    sample = sorted(random.Random(args.seed).sample(sorted(puzzles), args.sample))
    with args.baseline.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['id', 'program']:
            raise ValueError('baseline must have id,program columns')
        baseline = {}
        for row in reader:
            if row['id'] in baseline: raise ValueError(f"Duplicate baseline ID {row['id']}")
            baseline[row['id']] = json.loads(row['program'])
    if set(baseline) != set(puzzles):
        raise ValueError('baseline IDs do not match puzzles')
    sha = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    sections = []
    for number, ident in enumerate(sample, 1):
        puzzle, program = puzzles[ident], baseline[ident]
        trace = replay(puzzle, program)
        starts = json.loads(puzzle['starting_values'])
        targets = json.loads(puzzle['targets'])
        initial_hits = sorted(set(starts).intersection(targets))
        body = [f'## {number}. {ident}', '',
                f'- 初始寄存器：{", ".join(f"r{i}={v}" for i, v in enumerate(starts))}',
                f'- 目标数（{len(targets)} 个）：{", ".join(map(str, targets))}',
                f'- 初始值已覆盖的目标：{", ".join(map(str, initial_hits)) if initial_hits else "无"}',
                f'- value_limit：{puzzle["value_limit"]}；程序步数：{len(program)}', '',
                '| 步数 | 运算 | 结果和目标标记 |', '|---:|---|---|']
        for step, left, a, op, right, b, dest, value, marker in trace:
            body.append(f'| {step} | r{left} ({a}) {op} r{right} ({b}) | r{dest} = {value} {marker} |')
        sections.append('\n'.join(body))
    total = sum(len(baseline[i]) for i in sample)
    header = [f'# 随机 {len(sample)} 道计分题的完整操作序列', '',
              '数据来自本地竞赛题目文件；程序来自公开第三方 baseline，非本项目原创。',
              f'- 来源：[Hansen0223 固定版本]({SOURCE})',
              f'- baseline SHA-256：`{sha}`',
              f'- 抽样：从全部题号排序后，用 Python `random.Random({args.seed}).sample` 无放回抽取 {args.sample} 题，再按题号排序展示。',
              f'- 本样本总指令数：{total}；每题已通过本地回放检查。',
              '- `★ 首次命中` 表示该目标首次出现；`★ 再次出现` 表示此前已命中的目标再次出现。初始值里已有的目标在题目开头单独注明。',
              '- 操作数括号中的数字为运算前寄存器的值；结果在两个操作数读取后写入目标寄存器。', '',
              '## 目录', '']
    header.extend(f'- [{i}](#{n}-{i})' for n, i in enumerate(sample, 1))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(header) + '\n\n' + '\n\n'.join(sections) + '\n', encoding='utf-8')
    print(f'exported {len(sample)} cases, {total} instructions to {args.output}')

if __name__ == '__main__': main()
