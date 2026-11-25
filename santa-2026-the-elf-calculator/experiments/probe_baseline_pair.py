"""Compare single-target, two-target and full-puzzle costs on scored_0253."""
import csv
import json

from export_50_baseline_cases import DEFAULT_BASELINE, DEFAULT_PUZZLES, replay
from first_solver import validate
from target_meet_search import find_program


def read_case(path, ident):
    with path.open(newline='') as f:
        return next(row for row in csv.DictReader(f) if row['id'] == ident)


def compile_values(puzzle, steps, targets):
    """Keep the first recipe for each value, prune, then allocate by last use."""
    starts = json.loads(puzzle['starting_values'])
    available = set(starts)
    ordered = []
    for op, a, b, v in steps:
        if a not in available or b not in available:
            raise ValueError('input unavailable')
        if v not in available:
            ordered.append((op, a, b, v))
            available.add(v)
    if not set(targets) <= available:
        raise ValueError('target unavailable')
    needed = set(targets)
    retained = []
    for rule in reversed(ordered):
        op, a, b, v = rule
        if v in needed:
            retained.append(rule)
            needed.update((a, b))
    retained.reverse()
    registers = {v: i for i, v in enumerate(starts)}
    last_use = {v: i for i, (_, a, b, _) in enumerate(retained) for v in (a, b)}
    slots = set(range(int(puzzle['registers']))) - set(registers.values())
    for v in starts:
        if v not in last_use:
            slots.add(registers.pop(v))
    ops = []
    for i, (op, a, b, v) in enumerate(retained):
        left, right = registers[a], registers[b]
        for source in {a, b}:
            if last_use[source] == i:
                slots.add(registers.pop(source))
        if not slots:
            raise ValueError('register budget exceeded')
        dest = min(slots)
        ops.append([op, left, right, dest])
        if v in last_use:
            registers[v] = dest
            slots.remove(dest)
    validate(dict(puzzle, targets=json.dumps(targets)), ops)
    return ops


def main():
    ident = 'scored_0253'
    p = read_case(DEFAULT_PUZZLES, ident)
    program = json.loads(read_case(DEFAULT_BASELINE, ident)['program'])
    trace = replay(p, program)
    starts = json.loads(p['starting_values'])
    targets = json.loads(p['targets'])
    limit = int(p['value_limit'])
    original = [(op, a, b, v) for _, _, a, op, _, b, _, v, _ in trace]
    hit_order = [v for *_, v, mark in trace if mark == '★ 首次命中']
    dependencies = [set() for _ in range(int(p['registers']))]
    hits = {}
    for n, left, _, _, right, _, dest, v, mark in trace:
        dependencies[dest] = dependencies[left] | dependencies[right] | {n}
        if mark == '★ 首次命中':
            hits[v] = dependencies[dest]
    print('Original program', len(program))
    print('Steps needed by the first hit', sorted(hits[hit_order[0]]))
    print('Target dependency graphs containing step 1', sum(1 in deps for deps in hits.values()))
    first_deps = hits[hit_order[0]]
    rescheduled = [rule for n, rule in enumerate(original, 1) if n in first_deps]
    rescheduled.extend(rule for n, rule in enumerate(original, 1) if n not in first_deps)
    ops = compile_values(p, rescheduled, targets)
    hit_steps = [n for n, *_, mark in replay(p, ops) if mark == '★ 首次命中']
    print('Rescheduled first two hits', hit_steps[:2], 'total', len(ops))
    for order in (hit_order[:2], hit_order[1::-1]):
        pool = list(starts)
        steps = []
        for i, goal in enumerate(order):
            extra = find_program(goal, pool, limit, depth=4-i)
            if extra is None:
                raise ValueError('no short expression found')
            steps.extend(extra)
            pool.extend(v for _, _, _, v in extra)
            for op, a, b, v in extra:
                print(f'{a} {op} {b} = {v}')
            partial = compile_values(p, steps, order[:i+1])
            full = compile_values(p, steps+original, targets)
            print('Hit', goal, 'prefix', len(partial), 'all targets', len(full))


if __name__ == '__main__':
    main()
