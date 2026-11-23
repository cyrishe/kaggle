#!/usr/bin/env python3
"""Replay a reproducible sample and inspect instruction dependency sharing."""
import collections
import csv
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261123
SAMPLE_SIZE = 30
csv.field_size_limit(1_000_000)


def analyze(puzzle, program):
    starts = json.loads(puzzle['starting_values'])
    targets = set(json.loads(puzzle['targets']))
    limit = int(puzzle['value_limit'])
    registers = starts + [None] * (int(puzzle['registers']) - len(starts))
    versions = [None] * len(registers)
    descendants = collections.Counter()
    dependencies = []
    values = []
    first_cover = {}
    counts = collections.Counter()
    used_registers = set(range(len(starts)))
    for index, (op, left, right, dest) in enumerate(program):
        a, b = registers[left], registers[right]
        if a is None or b is None:
            raise ValueError(f'undefined register at step {index + 1}')
        sources = {v for v in (versions[left], versions[right]) if v is not None}
        for source in sources:
            descendants[source] += 1
        dependencies.append(sources)
        if op == '+': value = a + b
        elif op == '-': value = a - b
        elif op == '*': value = a * b
        elif op == '/' and b and a % b == 0: value = a // b
        else: raise ValueError(f'illegal operator/division at step {index + 1}')
        if not 0 < value <= limit: raise ValueError(f'out of bounds at step {index + 1}')
        counts[op] += 1
        if op == '*' and left == right: counts['square'] += 1
        used_registers.update((left, right, dest))
        registers[dest] = value
        versions[dest] = index
        values.append(value)
        if value in targets and value not in starts:
            first_cover.setdefault(value, index)
    if set(starts).intersection(targets) | first_cover.keys() != targets:
        raise ValueError('targets missing')
    ancestor_targets = [set() for _ in program]
    for target, index in first_cover.items():
        stack = [index]
        seen = set()
        while stack:
            node = stack.pop()
            if node in seen: continue
            seen.add(node)
            ancestor_targets[node].add(target)
            stack.extend(dependencies[node])
    shared = [i for i, hits in enumerate(ancestor_targets)
              if values[i] not in targets and len(hits) >= 2]
    coverage_order = list(first_cover)
    reused = [i for i, count in descendants.items() if count >= 2 and values[i] not in targets]
    return {
        'id': puzzle['id'], 'starting_values': starts,
        'targets': len(targets), 'instructions': len(program),
        'operations': {op: counts[op] for op in ('+', '-', '*', '/')},
        'squares': counts['square'], 'register_indices_used': len(used_registers),
        'first_target_step': min(first_cover.values(), default=-1) + 1,
        'last_target_step': max(first_cover.values(), default=-1) + 1,
        'target_order_is_sorted': coverage_order == sorted(coverage_order),
        'non_target_values_reused_by_2_instructions': len(reused),
        'non_target_values_ancestor_of_2_targets': len(shared),
        'shared_examples': [
            {'value': values[i], 'produced_at_step': i + 1,
             'target_descendants': len(ancestor_targets[i]),
             'direct_instruction_uses': descendants[i]}
            for i in sorted(shared, key=lambda i: (-len(ancestor_targets[i]), i))[:5]
        ],
    }


def main():
    with (ROOT / 'data/puzzles.csv').open(newline='') as stream:
        puzzles = {row['id']: row for row in csv.DictReader(stream)}
    selected = sorted(random.Random(SEED).sample(sorted(puzzles), SAMPLE_SIZE))
    with (ROOT / 'external/hansen_0652a700/submission.csv').open(newline='') as stream:
        programs = {row['id']: json.loads(row['program']) for row in csv.DictReader(stream)
                    if row['id'] in selected}
    records = [analyze(puzzles[ident], programs[ident]) for ident in selected]
    aggregate = {
        'seed': SEED, 'cases': len(records),
        'total_instructions': sum(r['instructions'] for r in records),
        'operations': dict(sum((collections.Counter(r['operations']) for r in records), collections.Counter())),
        'cases_with_intermediate_shared_between_targets': sum(r['non_target_values_ancestor_of_2_targets'] > 0 for r in records),
        'median_shared_intermediates': statistics.median(r['non_target_values_ancestor_of_2_targets'] for r in records),
        'sorted_target_order_cases': sum(r['target_order_is_sorted'] for r in records),
        'median_first_target_step': statistics.median(r['first_target_step'] for r in records),
    }
    output = ROOT / 'experiments/public_baseline_review_30.json'
    output.write_text(json.dumps({'aggregate': aggregate, 'cases': records}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    for r in records:
        print(r['id'], 'steps',r['instructions'],'targets',r['targets'],'shared',r['non_target_values_ancestor_of_2_targets'],'first',r['first_target_step'],'sorted',r['target_order_is_sorted'],'example',r['shared_examples'][:1])

if __name__ == '__main__':
    main()
