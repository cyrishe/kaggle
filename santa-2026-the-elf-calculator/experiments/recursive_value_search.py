#!/usr/bin/env python3
"""Search short integer expressions from values currently in registers."""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def one_step(values, limit):
    """Map each legal result to a representative one-instruction recipe."""
    result = {}
    for a in values:
        for b in values:
            choices = [('+', a + b), ('-', a - b), ('*', a * b)]
            if b and a % b == 0:
                choices.append(('/', a // b))
            for op, value in choices:
                if 0 < value <= limit and value not in values:
                    result.setdefault(value, (op, a, b, value))
    return result


def finish_from_one(x, target, known, limit):
    """Find all useful one-step equations containing x and a known value."""
    options = []
    if target > x and target - x in known:
        options.append(('+', x, target - x, target))
    if x > target and x - target in known:
        options.append(('-', x, x - target, target))
    if x + target in known:
        options.append(('-', x + target, x, target))
    if x and target % x == 0 and target // x in known:
        options.append(('*', x, target // x, target))
    if x % target == 0 and x // target in known:
        options.append(('/', x, x // target, target))
    if x * target <= limit and x * target in known:
        options.append(('/', x * target, x, target))
    # The first new value may be used twice.
    if x + x == target:
        options.append(('+', x, x, target))
    if x * x == target:
        options.append(('*', x, x, target))
    return options


def search(target, input_values, limit, depth=2):
    """Search legal expressions with at most three new operations.

    Depth two is complete within this restricted search: a one-instruction
    result may be combined with any starting value or itself. All steps must
    be positive integers no larger than the limit.
    """
    known = set(input_values)
    if not known or any(not 0 < x <= limit for x in known):
        raise ValueError('invalid input values')
    if not 0 < target <= limit or depth not in (1, 2, 3):
        raise ValueError('invalid target or depth')
    if target in known:
        return []
    first = one_step(known, limit)
    if target in first:
        return [first[target]]
    if depth == 1:
        return None
    for value, recipe in first.items():
        options = finish_from_one(value, target, known, limit)
        if options:
            return [recipe, options[0]]
    if depth == 2:
        return None
    # Two independently constructed one-step results, joined in the last step.
    first_values = set(first)
    for value, recipe in first.items():
        options = finish_from_one(value, target, first_values, limit)
        for last in options:
            other = last[2] if last[1] == value else last[1]
            if other != value and other in first:
                return [recipe, first[other], last]
    # One-operand backward expansion, then resolve the missing number in two steps.
    requirements = []
    for a in known:
        if target > a:
            requirements.append((target - a, ('+', a, target - a, target)))
        if a > target:
            requirements.append((a - target, ('-', a, a - target, target)))
        if target + a <= limit:
            requirements.append((target + a, ('-', target + a, a, target)))
        if target % a == 0:
            requirements.append((target // a, ('*', a, target // a, target)))
        if a % target == 0:
            requirements.append((a // target, ('/', a, a // target, target)))
        if target * a <= limit:
            requirements.append((target * a, ('/', target * a, a, target)))
    for required, last in requirements:
        if required in known or required in first:
            continue
        for value, recipe in first.items():
            options = finish_from_one(value, required, known, limit)
            if options:
                return [recipe, options[0], last]
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=int)
    parser.add_argument('values', type=int, nargs='+')
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--depth', type=int, default=2, choices=(1, 2, 3))
    args = parser.parse_args()
    path = search(args.target, args.values, args.limit, args.depth)
    if path is None:
        print('No solution within the searched depth')
    else:
        for op, a, b, value in path:
            print(f'{a} {op} {b} = {value}')
        print('steps:', len(path))

if __name__ == '__main__':
    main()
