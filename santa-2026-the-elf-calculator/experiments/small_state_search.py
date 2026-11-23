#!/usr/bin/env python3
"""Exact breadth-first search on small positive-integer calculator puzzles.

This bounded solver only adds values to unused registers. If it finds a solution
in k steps and the initial register count plus k is at most 48, then every legal
solution shorter than k can be represented without overwriting: keep the old
value and redirect each write to an unused register.
"""
import argparse
import collections
import csv
import json
import itertools
from pathlib import Path
from first_solver import validate

ROOT = Path(__file__).resolve().parent.parent


def successors(values, limit):
    for a, b in itertools.combinations_with_replacement(sorted(values), 2):
        candidates = [('+', a, b, a + b), ('*', a, b, a * b)]
        if b > a:
            candidates.append(('-', b, a, b - a))
        if b % a == 0:
            candidates.append(('/', b, a, b // a))
        for op, left, right, result in candidates:
            if 0 < result <= limit and result not in values:
                yield result, (op, left, right)


def backward_requirements(target, values, limit):
    """Generate the missing operand in one-step target equations."""
    candidates = set()
    for known in values:
        if target > known:
            candidates.add(('+', known, target - known))
        if known > target:
            candidates.add(('-', known, known - target))
        if target + known <= limit:
            candidates.add(('-', target + known, known))
        if target % known == 0:
            candidates.add(('*', known, target // known))
        if target * known <= limit:
            candidates.add(('/', target * known, known))
    return sorted(candidates)


def search(puzzle, max_nodes):
    starts = json.loads(puzzle['starting_values'])
    targets = set(json.loads(puzzle['targets']))
    limit = int(puzzle['value_limit'])
    initial_values = frozenset(starts)
    initial_covered = frozenset(targets & initial_values)
    initial_state = (initial_values, initial_covered)
    parents = {initial_state: None}
    queue = collections.deque([initial_state])
    final = None
    while queue:
        state = queue.popleft()
        values, covered = state
        if covered == targets:
            final = state
            break
        if len(values) >= int(puzzle['registers']):
            continue
        for value, expression in successors(values, limit):
            next_state = (values | {value}, covered | ({value} & targets))
            if next_state in parents:
                continue
            if len(parents) >= max_nodes:
                raise RuntimeError(f'state limit reached: {max_nodes}')
            parents[next_state] = (state, value, expression)
            queue.append(next_state)
    if final is None:
        raise RuntimeError('no solution found within the search bounds')
    path = []
    while parents[final] is not None:
        previous, value, expression = parents[final]
        path.append((value, expression))
        final = previous
    path.reverse()
    registers = {value:index for index, value in enumerate(starts)}
    program = []
    for value, (op, left, right) in path:
        destination = len(starts) + len(program)
        if destination >= int(puzzle['registers']):
            raise RuntimeError('output exceeds register count')
        program.append([op, registers[left], registers[right], destination])
        registers[value] = destination
    validate(puzzle, program)
    exact = len(starts) + len(program) <= int(puzzle['registers'])
    return program, path, len(parents), exact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', default='practice_0039')
    parser.add_argument('--max-nodes', type=int, default=500000)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.max_nodes < 1:
        parser.error('--max-nodes must be positive')
    with (ROOT / 'data/practice_puzzles.csv').open(newline='') as f:
        puzzle = next((row for row in csv.DictReader(f) if row['id'] == args.id), None)
    if puzzle is None:
        parser.error(f'unknown practice puzzle {args.id}')
    program, path, states, exact = search(puzzle, args.max_nodes)
    for step, (value, (op, left, right)) in enumerate(path, 1):
        print(f'{step}: {left} {op} {right} = {value}')
    print(f'{args.id}: {len(program)} instructions, {states} states, global shortest proven: {exact}')
    if path:
        final_target = path[-1][0]
        known = set(json.loads(puzzle['starting_values'])) | {value for value, _ in path[:-1]}
        matches = [c for c in backward_requirements(final_target, known, int(puzzle['value_limit']))
                   if c[1] in known and c[2] in known]
        print(f'Backward one-step matches for {final_target}: {matches}')
    if args.output:
        args.output.write_text(json.dumps(program, separators=(',', ':')) + '\n')

if __name__ == '__main__':
    main()
