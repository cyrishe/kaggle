"""Compare smoothness of large official targets with locally perturbed controls."""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from factor_gap_null import ROOT, SEED, bounds, read

PRIMES = [p for p in range(2, 98) if all(p%d for d in range(2, int(p**0.5)+1))]


def classify(n):
    rest = n
    for p in PRIMES:
        while rest % p == 0:
            rest //= p
        if rest == 1:
            break
    return (rest == 1, rest != n)


def main():
    tables = {}
    groups = defaultdict(list)
    groups['scored'] = read('puzzles.csv')
    for r in read('practice_puzzles.csv'):
        groups[r['family']].append(r)
    for family, rows in groups.items():
        actual = Counter()
        rounds = 39
        controls = [0]*rounds
        for row in rows:
            targets = json.loads(row['targets'])
            rng = random.Random(f"smooth-{SEED}-{row['id']}")
            for t,(lo,hi) in zip(targets,bounds(targets,int(row['value_limit']))):
                if t < 10**6:
                    continue
                lo = max(lo, 10**6)
                smooth, small = classify(t)
                actual.update({'targets':1,'fully_smooth':smooth,'has_small_prime':small})
                for j in range(rounds):
                    controls[j] += classify(rng.randint(lo,hi))[0]
        tables[family] = dict(actual=actual,controls=controls)
        print(family,actual,'control mean',mean(controls),'range',min(controls),max(controls))
    (ROOT/'reports/target_smoothness_null.json').write_text(json.dumps(tables,indent=2)+'\n')


if __name__ == '__main__':
    main()
