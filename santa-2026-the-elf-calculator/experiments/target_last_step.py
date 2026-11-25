"""Classify the first producer of each target in the versioned baseline lineage."""
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from baseline_lineage import DB, DEFAULT_PUZZLES, shallow


def operands_at_depth_three(starts, limit):
    """Test F3 membership by querying F2 for the other operand of a legal recipe."""
    reachable, _ = shallow(starts, limit, 2)
    keys = tuple(reachable)
    cache = dict.fromkeys(keys, True)

    def contains(value):
        if value not in cache:
            cache[value] = any(
                value + a in reachable or abs(value - a) in reachable
                or value * a in reachable
                or (value % a == 0 and value // a in reachable)
                or (a % value == 0 and a // value in reachable)
                for a in keys
            )
        return cache[value]

    return contains


def analyze():
    counts = Counter()
    examples = {}
    with DEFAULT_PUZZLES.open() as source:
        official = {p['id']: p for p in csv.DictReader(source)}
    with sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        metadata = dict(db.execute('SELECT * FROM metadata'))
        assert hashlib.sha256(DEFAULT_PUZZLES.read_bytes()).hexdigest() == metadata['puzzles_sha256']
        ids = {p[0] for p in db.execute('SELECT id FROM puzzles')}
        assert ids == official.keys()
        for ident, puzzle in official.items():
            goals = set(json.loads(puzzle['targets']))
            starts = json.loads(puzzle['starting_values'])
            shallow_value = operands_at_depth_three(starts, int(puzzle['value_limit']))
            rows = db.execute('SELECT * FROM nodes WHERE puzzle=? ORDER BY step', (ident,))
            seen = set()
            nodes = {}
            registers = {}
            for row in rows:
                step, target, op = row['step'], row['value'], row['op']
                nodes[step] = row
                counts['instructions'] += int(op is not None)
                if target in goals and target not in seen:
                    seen.add(target)
                    counts[op or 'initial'] += 1
                    if op is not None:
                        left, right = (nodes[row[k]] for k in ('left_step', 'right_step'))
                        assert registers[left['dest']] == left['value']
                        assert registers[right['dest']] == right['value']
                        live = set(registers.values())
                        can_multiply = any(target % a == 0 and target // a in live for a in live)
                        counts['live_product'] += can_multiply
                        if op == '*':
                            assert can_multiply
                        elif can_multiply:
                            counts['alternative_product_' + op] += 1
                    if op in ('+', '-', '*'):
                        small, large = sorted((left, right), key=lambda x: (x['value'], x['depth']))
                        smaller = small['value']
                        example = [ident, step, left['value'], op, right['value'], target,
                                   left['depth'], right['depth']]
                        if op == '*':
                            for threshold in (10, 100, 1000, 10000, 1000000):
                                if smaller >= threshold:
                                    counts[f'factors_ge_{threshold}'] += 1
                            counts['square'] += left['value'] == right['value']
                            if smaller >= 10000:
                                examples.setdefault('large_product', example)
                        else:
                            shallow_parent = min(left['depth'], right['depth']) <= 3
                            shallow_small = small['depth'] <= 3
                            possible_small = shallow_value(smaller)
                            possible_any = possible_small or shallow_value(large['value'])
                            assert not shallow_parent or possible_any
                            assert not shallow_small or possible_small
                            group = 'shallow' if shallow_parent else 'both_deep'
                            counts[op + '_' + group] += 1
                            counts['smaller_shallow'] += shallow_small
                            counts['possible_shallow'] += possible_any
                            counts['possible_smaller_shallow'] += possible_small
                            for scale in (1000, 100, 20, 10):
                                if smaller * scale <= target:
                                    counts[f'near_{scale}'] += 1
                                    counts[f'small_shallow_near_{scale}'] += shallow_small
                                    counts[f'possible_small_near_{scale}'] += possible_small
                                    counts[f'{group}_near_{scale}'] += 1
                            product_parent = left['op'] == '*' or right['op'] == '*'
                            counts['product_parent_addsub'] += product_parent
                            counts['large_product_parent_addsub'] += large['op'] == '*'
                            if smaller * 100 <= target:
                                counts['near_1pct_large_product'] += large['op'] == '*'
                                counts['near_1pct_large_product_small_F3'] += (
                                    large['op'] == '*' and possible_small)
                                for bound in (10, 1000, 1000000):
                                    counts[f'near_1pct_abs_le_{bound}'] += smaller <= bound
                            counts['product_plus_F3_residual'] += (
                                (large['op'] == '*' and possible_small) or
                                (small['op'] == '*' and shallow_value(large['value'])))
                            if large['op'] == '*' and smaller * 100 <= target and target > 10**6:
                                examples.setdefault('near_product', example + [
                                    nodes[large['left_step']]['value'], nodes[large['right_step']]['value']])
                            if not possible_any and smaller * 10 > target and target > 10**6:
                                examples.setdefault('deep_pair', example)
                registers[row['dest']] = target
            assert seen == goals, ident
            counts['targets'] += len(goals)
    assert sum(counts[k] for k in ('initial', '+', '-', '*', '/')) == counts['targets']
    return dict(puzzles=len(official), source=metadata, counts=dict(counts), examples=examples)


if __name__ == '__main__':
    report = analyze()
    out = Path(DB).with_name('target_last_step.json')
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
