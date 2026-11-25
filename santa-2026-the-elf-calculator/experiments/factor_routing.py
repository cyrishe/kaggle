"""Find exact and translated common factors from the puzzle alone, then classify target links."""
import csv
import json
import math
import random
from collections import Counter, defaultdict
from itertools import combinations

from baseline_lineage import DB, DEFAULT_PUZZLES
from discover_patterns import short_recipes, target_links
from factor_gap_null import bounds
from target_multiplier_scan import divisors


def exact_groups(goals, minimum):
    gcds = {math.gcd(a, b) for a, b in combinations(goals, 2)}
    factors = {f for g in gcds if g >= minimum for f in divisors(g) if f >= minimum}
    groups = []
    for f in factors:
        members = tuple(t for t in goals if t > f and t % f == 0)
        if len(members) >= 2:
            groups.append((f, 0, members))
    return sorted(groups, key=lambda g: (-len(g[2]), -g[0]))


def residue_groups(goals, minimum, threshold):
    # Three members in a residue class witness the factor in a GCD of two differences.
    if len(goals) < threshold:
        return []
    gcds = {math.gcd(b-a, c-b) for a, b, c in combinations(goals, 3)}
    factors = {f for g in gcds if g >= minimum for f in divisors(g) if f >= minimum}
    groups = []
    for f in factors:
        classes = defaultdict(list)
        for goal in goals:
            classes[goal % f].append(goal)
        groups.extend((f, r, tuple(ts)) for r, ts in classes.items() if r and len(ts) >= threshold)
    return sorted(groups, key=lambda g: (-len(g[2]), -g[0], g[1]))


def features(puzzle):
    goals = sorted(json.loads(puzzle['targets']))
    starts = json.loads(puzzle['starting_values'])
    limit = int(puzzle['value_limit'])
    minimum = max(100, max(starts)+1)
    threshold = max(3, (len(goals)+4)//5)
    factors = exact_groups(goals, minimum)
    exact = [g for g in factors if len(g[2]) >= threshold]
    relaxed = [g for g in factors if len(g[2]) >= max(3, (len(goals)+9)//10)]
    translated = residue_groups(goals, minimum, max(4, threshold))
    cheap = short_recipes(starts, limit)
    links = target_links(goals, cheap, limit)
    counts = {name:len({e['to'] for e in links if (e['multiplier']==1) == (name=='delta')})
              for name in ('delta', 'affine')}
    best = max(counts, key=counts.get)
    if exact:
        route = 'factor'
    elif translated:
        route = 'residue'
    elif counts[best] >= threshold:
        route = best
    elif relaxed:
        route = 'weak_factor'
    else:
        route = 'general'
    return dict(route=route, n=len(goals), required=threshold, exact=exact, relaxed=relaxed, translated=translated,
                best_exact_by_size={f:max((len(g[2]) for g in factors if g[0]>=f), default=0)
                                    for f in (100,1000)}, link_coverage=counts)


def main():
    cases = {}
    controls = Counter()
    with DEFAULT_PUZZLES.open() as file:
        for p in csv.DictReader(file):
            row = features(p)
            cases[p['id']] = row
            goals = sorted(json.loads(p['targets']))
            limit = int(p['value_limit'])
            minimum = max(100, max(json.loads(p['starting_values']))+1)
            intervals = bounds(goals, limit)
            rng = random.Random(p['id']+'-factor-routing')
            for _ in range(5):
                sampled = [rng.randint(lo,hi) for lo,hi in intervals]
                direct = exact_groups(sampled, minimum)
                if direct and len(direct[0][2]) >= max(3, (len(goals)+9)//10):
                    controls['at_least_10pct'] += 1
                if direct and len(direct[0][2]) >= row['required']:
                    controls['factor'] += 1
                elif residue_groups(sampled, minimum, max(4, row['required'])):
                    controls['residue'] += 1
    out = dict(cases=cases, null_replicates=5, null=dict(controls))
    DB.with_name('factor_routing.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    print(Counter(r['route'] for r in cases.values()), controls)


if __name__ == '__main__':
    main()
