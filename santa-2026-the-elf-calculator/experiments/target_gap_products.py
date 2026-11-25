"""Find target-pair differences that factor into two cheaply constructible values."""
import argparse
import json
from itertools import combinations

from export_50_baseline_cases import DEFAULT_PUZZLES
from probe_baseline_pair import read_case
from target_meet_search import catalogue


def scan(starts, targets, limit, depth):
    recipes = catalogue(starts, limit, depth)
    dependencies = {}
    for value, recipe in recipes.items():
        if recipe is None:
            dependencies[value] = set()
        else:
            _, a, b = recipe
            dependencies[value] = {value} | dependencies[a] | dependencies[b]
    factors = sorted(v for v in recipes if v > 1)
    for low, high in combinations(sorted(set(targets)), 2):
        gap = high - low
        for a in factors:
            if a * a > gap:
                break
            b, remainder = divmod(gap, a)
            if remainder == 0 and b in recipes:
                # Construct factors once, then multiply and add to the available lower target.
                steps = len(dependencies[a] | dependencies[b]) + 2
                yield low, high, a, b, steps


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id')
    parser.add_argument('--depth', type=int, default=3)
    args = parser.parse_args()
    puzzle = read_case(DEFAULT_PUZZLES, args.id)
    for low, high, a, b, steps in scan(json.loads(puzzle['starting_values']),
                                       json.loads(puzzle['targets']),
                                       int(puzzle['value_limit']), args.depth):
        print(f'{high} = {low} + {a} * {b}   ({steps} steps with the lower target available)')
