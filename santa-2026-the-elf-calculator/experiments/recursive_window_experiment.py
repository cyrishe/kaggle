#!/usr/bin/env python3
"""Search replacement computations for residuals in existing programs."""
import csv
import json
import sys
from pathlib import Path
from first_solver import validate
from recursive_value_search import search

ROOT = Path(__file__).resolve().parent.parent
IDS = {'scored_0001','scored_0112','scored_0223','scored_0334','scored_0445',
       'scored_0556','scored_0667','scored_0778','scored_0889','scored_1000'}
csv.field_size_limit(1_000_000)


def replay_values(puzzle, program):
    starts = json.loads(puzzle['starting_values'])
    values = starts + [None] * (int(puzzle['registers']) - len(starts))
    snapshots = [values.copy()]
    for op, left, right, dest in program:
        a, b = values[left], values[right]
        if op == '+': value = a + b
        elif op == '-': value = a - b
        elif op == '*': value = a * b
        elif op == '/': value = a // b
        else: raise ValueError('unknown operation')
        values[dest] = value
        snapshots.append(values.copy())
    return snapshots


def synthesize_recipe(recipe, values, scratch, spare):
    locations = {v:i for i, v in enumerate(values) if v is not None and i not in (scratch, spare)}
    output = []
    for index, (op, a, b, result) in enumerate(recipe):
        if a not in locations or b not in locations:
            return None
        dest = scratch if index == len(recipe) - 1 else spare
        if dest is None:
            return None
        output.append([op, locations[a], locations[b], dest])
        for value, loc in list(locations.items()):
            if loc == dest: del locations[value]
        locations[result] = dest
    return output


def improve(puzzle, original):
    program = original
    changes = []
    max_passes = 12
    for _ in range(max_passes):
        snapshots = replay_values(puzzle, program)
        targets = set(json.loads(puzzle['targets']))
        limit = int(puzzle['value_limit'])
        replaced = False
        for end, (op, left, right, dest) in enumerate(program):
            if snapshots[end + 1][dest] not in targets or op not in ('+', '-', '*'):
                continue
            for scratch in (left, right):
                start = end
                while start > 0 and program[start - 1][3] == scratch and end - start < 8:
                    start -= 1
                old_count = end - start
                if old_count < 2 or any(snapshots[j + 1][scratch] in targets for j in range(start, end)):
                    continue
                desired = snapshots[end][scratch]
                other = right if scratch == left else left
                if scratch == dest or dest == other:
                    continue
                # Recompute with both the residual scratch register and target destination
                # unavailable as initial inputs, since the replacement may overwrite them.
                known = [v for i, v in enumerate(snapshots[start])
                         if v is not None and i not in (scratch, dest)]
                if not known: continue
                recipe = search(desired, known, limit, min(3, old_count - 1))
                if recipe is None or len(recipe) >= old_count: continue
                replacement = synthesize_recipe(recipe, snapshots[start], scratch, dest)
                if replacement is None: continue
                candidate = program[:start] + replacement + program[end:]
                try:
                    validate(puzzle, candidate)
                except (ValueError, TypeError, IndexError):
                    continue
                changes.append({'target': snapshots[end + 1][dest], 'residual': desired,
                                'old_steps': old_count, 'new_steps': len(replacement),
                                'recipe': recipe})
                program = candidate
                replaced = True
                break
            if replaced: break
        if not replaced: break
    validate(puzzle, program)
    return program, changes


def main():
    with (ROOT / 'data/puzzles.csv').open(newline='') as f:
        puzzles = {r['id']:r for r in csv.DictReader(f) if r['id'] in IDS}
    with (ROOT / 'experiments/deep_ten_best.csv').open(newline='') as f:
        programs = {r['id']:json.loads(r['program']) for r in csv.DictReader(f) if r['id'] in IDS}
    outputs = []
    report = []
    for ident in sorted(puzzles):
        old = programs[ident]
        new, changes = improve(puzzles[ident], old)
        report.append({'id':ident, 'before':len(old), 'after':len(new), 'changes':changes})
        outputs.append({'id':ident, 'program':json.dumps(new, separators=(',', ':'))})
        print(ident, len(old), '->', len(new), 'replacements', len(changes), flush=True)
    (ROOT / 'experiments/recursive_window_report.json').write_text(json.dumps(report, indent=2)+'\n')
    with (ROOT / 'experiments/recursive_window_programs.csv').open('w', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=['id','program']);writer.writeheader();writer.writerows(outputs)

if __name__ == '__main__': main()
