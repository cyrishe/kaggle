"""Matched random controls for cheap target and target-gap product decompositions."""
import csv
import json
import random
import statistics
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from target_meet_search import catalogue

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261124


def read(name):
    with (ROOT / 'data' / name).open() as f:
        return list(csv.DictReader(f))


def bounds(targets, limit):
    intervals = []
    for i, t in enumerate(targets):
        gaps = ([t-targets[i-1]] if i else []) + ([targets[i+1]-t] if i+1<len(targets) else [])
        radius = min([t//100] + [gap//4 for gap in gaps])
        intervals.append((max(1,t-radius), min(limit,t+radius)))
    return intervals


def simulate(binary, row, repeats, stride=1):
    targets = sorted(json.loads(row['targets']))
    limit = int(row['value_limit'])
    rng = random.Random(f"{SEED}-{row['id']}-{stride}")
    factors = sorted(v for v in catalogue(json.loads(row['starting_values']), limit, 3) if v>1)
    limits = bounds(targets, limit)
    lines = [f'{len(factors)} {len(targets)} {repeats+1}', ' '.join(map(str, factors)), ' '.join(map(str, targets))]
    for _ in range(repeats):
        sample = [rng.randrange(lo+(t-lo)%stride, hi+1, stride) for t,(lo,hi) in zip(targets, limits)]
        lines.append(' '.join(map(str,sample)))
    output = subprocess.check_output([str(binary)], input='\n'.join(lines)+'\n', text=True)
    actual, *random_rows = [list(map(int, line.split())) for line in output.splitlines()]
    return {'id':row['id'], 'n':len(targets), 'factor_count':len(factors),
            'fixed_targets':sum(hi==lo for lo,hi in limits), 'real':actual, 'controls':random_rows}


def main():
    rng = random.Random(SEED)
    groups = defaultdict(list)
    for r in read('practice_puzzles.csv'):
        groups[r['family']].append(r)
    scored = read('puzzles.csv')
    focus = next(r for r in scored if r['id']=='scored_0253')
    jobs = [('scored_0253', [focus], 999, 1), ('0253_same_parity',[focus],999,2),
            ('scored_random',rng.sample([r for r in scored if r != focus],60),39,1)]
    for family in ('shared','multiplicative','mixed','independent'):
        jobs.append((family,rng.sample(groups[family],12),39,1))
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp)/'counter'
        subprocess.run(['c++','-std=c++17','-O3',str(Path(__file__).with_suffix('.cpp')),'-o',str(binary)],check=True)
        for name, rows, repeats, stride in jobs:
            trials = [simulate(binary,row,repeats,stride) for row in rows]
            actual = [sum(t['real'][i] for t in trials) for i in range(2)]
            controls = [[sum(t['controls'][j][i] for t in trials) for j in range(repeats)] for i in range(2)]
            summary = dict(real=actual, mean=[statistics.mean(c) for c in controls],
                           at_least_real=[sum(v>=a for v in c) for c,a in zip(controls,actual)],
                           at_least_one=[sum(v>=1 for v in c) for c in controls],
                           maxima=[max(c) for c in controls], repeats=repeats)
            print(name,summary,flush=True)
            result[name] = dict(summary=summary,trials=trials)
    (ROOT/'reports/factor_gap_null.json').write_text(json.dumps(result,separators=(',',':'))+'\n')


if __name__ == '__main__':
    main()
