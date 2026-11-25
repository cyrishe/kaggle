"""Reproduce the fixed-suffix search with Python 3 and a C++17 compiler."""
import json
from pathlib import Path
import subprocess
import tempfile

from export_50_baseline_cases import DEFAULT_BASELINE, DEFAULT_PUZZLES, replay
from first_solver import validate
from probe_baseline_pair import read_case

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).with_name('boundary_meet_search.cpp')
RESULT = ROOT / 'reports/scored_0253_boundary.json'
CUT = 17


def live_inputs(trace, cut):
    written = set()
    live = {}
    reads = {}
    for step, left, a, _, right, b, dest, _, _ in trace[cut:]:
        for reg, value in ((left, a), (right, b)):
            if reg not in written:
                live[reg] = value
                reads.setdefault(reg, []).append(step)
        written.add(dest)
    return live, reads


def encode_prefix(steps, starts, live):
    # Reserve the destination expected by the untouched suffix for each live output.
    expected = {v: reg for reg, v in live.items()}
    where = {v: reg for reg, v in enumerate(starts)}
    scratch = iter(sorted(set(range(48)) - set(expected.values()) - set(where.values())))
    ops = []
    for op, a, b, v in steps:
        dest = expected[v] if v in expected else next(scratch)
        ops.append([op, where[a], where[b], dest])
        where[v] = dest
    if any(where[v] != reg for reg, v in live.items()):
        raise ValueError('Boundary layout differs from the original')
    return ops


def search(binary, case, novel, savings, streak=None):
    args = [str(binary), str(novel), str(savings)]
    if streak is not None:
        args.append(str(streak))
    lines = subprocess.check_output(args, input=case, text=True).splitlines()
    status, subsets, states = lines[0].split()
    steps = []
    for line in lines[1:]:
        op, a, b, v = line.split()
        steps.append((op, int(a), int(b), int(v)))
    return dict(novel=novel, savings=savings, max_helpers_before_unlock=streak,
                status=status, subsets=int(subsets), calls=int(states)), steps


def main():
    ident = 'scored_0253'
    puzzle = read_case(DEFAULT_PUZZLES, ident)
    base = json.loads(read_case(DEFAULT_BASELINE, ident)['program'])
    trace = replay(puzzle, base)
    starts = json.loads(puzzle['starting_values'])
    live, reads = live_inputs(trace, CUT)
    values = [row[7] for row in trace[:CUT]]
    if len(set(starts + values)) != len(starts) + CUT:
        raise ValueError('This experiment requires distinct prefix values')
    required = set(live.values()) | (set(values) & set(json.loads(puzzle['targets'])))
    data = [f"{puzzle['value_limit']} {len(starts)}", ' '.join(map(str, starts)), str(CUT)]
    data.extend(f'{v} {int(v in required)}' for v in values)
    case = '\n'.join(data) + '\n'
    trials = []
    best = base
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / 'search'
        subprocess.run(['c++', '-std=c++17', '-O3', str(SOURCE), '-o', str(binary)], check=True)
        schedule = [(n, 1, None) for n in range(4)] + [(4, 1, 3), (5, 1, 3), (1, 0, None)]
        for novel, savings, streak in schedule:
            trial, steps = search(binary, case, novel, savings, streak)
            trials.append(trial)
            print(trial, flush=True)
            if trial['status'] == 'FOUND':
                program = encode_prefix(steps, starts, live) + base[CUT:]
                validate(puzzle, program)
                if len(program) <= len(best):
                    best = program
    # Independently replay the local four-instruction replacement in original register slots.
    alternative = base[:13] + [['+', 4, 15, 18], ['-', 16, 18, 18],
                               ['*', 18, 13, 18], ['-', 18, 16, 17]] + base[CUT:]
    arithmetic_trace = replay(puzzle, alternative)
    state = dict(enumerate(starts))
    for row in arithmetic_trace[:CUT]:
        state[row[6]] = row[7]
    assert all(state[r] == v for r, v in live.items()) and alternative[CUT:] == base[CUT:]
    result = dict(id=ident, baseline_steps=len(base), cut=CUT,
                  live=[dict(register=r, value=v, suffix_reads=reads[r]) for r,v in sorted(live.items())],
                  trials=trials, best_found_steps=len(best), search_witness=best,
                  four_step_alternative=alternative,
                  validated=validate(puzzle,best), alternative_validated=validate(puzzle,alternative))
    RESULT.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(RESULT)


if __name__ == '__main__':
    main()
