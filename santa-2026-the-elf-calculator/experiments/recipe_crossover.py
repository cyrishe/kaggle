"""Cross two verified programs by searching choices of concrete, observed recipes."""
import argparse
import csv
import json
import random
from collections import defaultdict
from itertools import product
from math import prod
from pathlib import Path

from export_50_baseline_cases import DEFAULT_PUZZLES, replay
from probe_baseline_pair import compile_values


def crossover(puzzle, parents, budget):
    recipes = defaultdict(list)
    starts = set(json.loads(puzzle['starting_values']))
    targets = json.loads(puzzle['targets'])
    incumbent = min(parents, key=len)
    for program in sorted(parents, key=len):
        for _, _, a, op, _, b, _, value, _ in replay(puzzle, program):
            if value in starts:
                continue
            if op in ('+', '*') and a > b:
                a, b = b, a
            rule = (op, a, b, value)
            if rule not in recipes[value]:
                recipes[value].append(rule)
    branches = [v for v in recipes if len(recipes[v]) > 1]
    sizes = [len(recipes[v]) for v in branches]
    possible = prod(sizes)
    rng = random.Random(puzzle['id'])
    if possible <= budget:
        choices = product(*(range(n) for n in sizes))
    else:
        samples = {tuple(0 for n in sizes)}
        for i in range(len(sizes)):
            for k in range(1, sizes[i]):
                if len(samples) < budget:
                    samples.add(tuple(k if j == i else 0 for j in range(len(sizes))))
        while len(samples) < budget:
            samples.add(tuple(rng.randrange(n) for n in sizes))
        choices = sorted(samples)
    selected = {v: rules[0] for v, rules in recipes.items()}
    min_nodes = None
    for indices in choices:
        for v, i in zip(branches, indices):
            selected[v] = recipes[v][i]
        placed = set(starts)
        active = set()
        steps = []

        def visit(v):
            if v in placed:
                return True
            if v in active:
                return False
            active.add(v)
            rule = selected[v]
            if not visit(rule[1]) or not visit(rule[2]):
                return False
            steps.append(rule)
            placed.add(v)
            active.remove(v)
            return True

        if not all(visit(t) for t in targets):
            continue
        min_nodes = len(steps) if min_nodes is None else min(min_nodes, len(steps))
        if len(steps) < len(incumbent):
            try:
                candidate = compile_values(puzzle, steps, targets)
            except ValueError as error:
                if str(error) != 'register budget exceeded':
                    raise
                continue
            incumbent = candidate
    return incumbent, dict(combinations=possible, tested=min(possible, budget), min_nodes=min_nodes)


def indexed(path):
    with path.open(newline='') as f:
        return {r['id']: r for r in csv.DictReader(f)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('ids', nargs='+')
    parser.add_argument('--budget', type=int, default=4096)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.budget < 1:
        parser.error('budget must be positive')
    first, second, puzzles = map(indexed, (args.first, args.second, DEFAULT_PUZZLES))
    output = {}
    for ident in args.ids:
        parents = [json.loads(rows[ident]['program']) for rows in (first, second)]
        program, meta = crossover(puzzles[ident], parents, args.budget)
        result = dict(parents=list(map(len, parents)), best=len(program), **meta)
        print(ident, result, flush=True)
        output[ident] = result
        if len(program) < min(map(len, parents)):
            result['program'] = program
    if args.output:
        args.output.write_text(json.dumps(output, indent=2)+'\n')


if __name__ == '__main__':
    main()
