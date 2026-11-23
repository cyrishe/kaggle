#!/usr/bin/env python3
"""Replay 30 new randomly chosen public solutions and inspect their endpoints."""
import collections
import csv
import json
import random
import statistics
from pathlib import Path
from review_public_baseline import analyze

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261124
csv.field_size_limit(1_000_000)


def detailed_trace(puzzle, program):
    starts = json.loads(puzzle['starting_values'])
    targets = set(json.loads(puzzle['targets']) )
    covered = targets.intersection(starts)
    values = starts + [None] * (int(puzzle['registers']) - len(starts))
    versions = [None] * len(values)
    uses = collections.Counter()
    trace = []
    for step, (op, left, right, dest) in enumerate(program, 1):
        a, b = values[left], values[right]
        if a is None or b is None: raise ValueError('undefined source')
        for version in set((versions[left], versions[right])) - {None}:
            uses[version] += 1
        if op == '+': result = a + b
        elif op == '-': result = a - b
        elif op == '*': result = a * b
        elif op == '/' and b and a % b == 0: result = a // b
        else: raise ValueError('invalid operation')
        if not 1 <= result <= int(puzzle['value_limit']): raise ValueError('out of range')
        is_new_target = result in targets and result not in covered
        covered.add(result) if result in targets else None
        trace.append({'step': step, 'operator': op, 'a': a, 'b': b, 'result': result,
                      'dest': dest, 'new_target': is_new_target})
        values[dest] = result
        versions[dest] = step
    if covered != targets: raise ValueError('uncovered target')
    for item in trace:
        item['direct_later_uses'] = uses[item['step']]
    first = trace[:5]
    last = trace[-5:]
    return {'id':puzzle['id'], 'initial':starts, 'steps':len(trace),
            'first':first, 'last':last,
            'last_is_new_target':trace[-1]['new_target'] if trace else False,
            'last5_target_count':sum(x['new_target'] for x in last),
            'first5_target_count':sum(x['new_target'] for x in first),
            'first5_later_reused':sum(x['direct_later_uses'] > 0 for x in first),
            'trace':trace}


def main():
    previous = json.loads((ROOT / 'experiments/public_baseline_review_30.json').read_text())
    previous_ids = {r['id'] for r in previous['cases']}
    with (ROOT / 'data/puzzles.csv').open(newline='') as f:
        puzzles = {r['id']:r for r in csv.DictReader(f)}
    selected = sorted(random.Random(SEED).sample(sorted(set(puzzles) - previous_ids), 30))
    with (ROOT / 'external/hansen_0652a700/submission.csv').open(newline='') as f:
        programs = {r['id']:json.loads(r['program']) for r in csv.DictReader(f) if r['id'] in selected}
    cases = [detailed_trace(puzzles[i], programs[i]) for i in selected]
    for c in cases: analyze(puzzles[c['id']], programs[c['id']])
    first_ops = collections.Counter(c['first'][0]['operator'] for c in cases)
    last_ops = collections.Counter(c['last'][-1]['operator'] for c in cases)
    first_one = sum(c['first'][0]['result']==1 for c in cases)
    first_start_sources = sum(c['first'][0]['a'] in c['initial'] and c['first'][0]['b'] in c['initial'] for c in cases)
    aggregate = {'seed':SEED, 'sample_count':len(cases), 'excluded_previous':len(previous_ids),
                 'first_operators':dict(first_ops),'first_result_one':first_one,
                 'first_uses_start_values':first_start_sources,'last_operators':dict(last_ops),
                 'last_is_new_target_count':sum(c['last_is_new_target'] for c in cases),
                 'first5_new_targets_total':sum(c['first5_target_count'] for c in cases),
                 'first5_total_instructions':sum(len(c['first']) for c in cases),
                 'first5_direct_reused_total':sum(c['first5_later_reused'] for c in cases),
                 'last5_new_targets_total':sum(c['last5_target_count'] for c in cases),
                 'last5_total_instructions':sum(len(c['last']) for c in cases)}
    path=ROOT/'experiments/public_initial_final_review_30.json'
    path.write_text(json.dumps({'aggregate':aggregate,'cases':cases},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(aggregate,ensure_ascii=False,indent=2))
    for c in cases:
        print(c['id'],c['steps'],'first:', [(x['operator'],x['a'],x['b'],x['result']) for x in c['first'][:2]],'last:', [(x['operator'],x['a'],x['b'],x['result'],x['new_target']) for x in c['last'][-2:]])

if __name__ == '__main__': main()
