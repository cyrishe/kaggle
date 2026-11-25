"""Blind scan of shifted target-pair GCDs. Baseline lineage is used only for evaluation."""
import csv
import json
import math
import random
from functools import lru_cache
from itertools import combinations,product
from baseline_lineage import DB, DEFAULT_PUZZLES
from factor_gap_null import bounds


@lru_cache(maxsize=32768)
def divisors(value):
    result=[1]
    factor=2
    while factor*factor<=value:
        if value%factor==0:
            previous=result.copy()
            power=1
            while value%factor==0:
                value//=factor
                power*=factor
                result.extend(n*power for n in previous)
        factor=3 if factor==2 else factor+2
    if value>1:
        result.extend([n*value for n in result])
    return tuple(result)


def scan(goals,limit,minimum):
    shifts=[[(t-r,r) for r in (0,1,-1,2,-2) if 0<t-r<=limit] for t in goals]
    factors=set()
    for left,right in combinations(shifts,2):
        for (a,_),(b,_) in product(left,right):
            f=math.gcd(a,b)
            if f>=minimum:
                factors.add(f)
    # Every factor covering two targets divides a shifted pair GCD; the GCD itself
    # can be a larger multiple which covers fewer targets.
    factors={d for g in factors for d in divisors(g) if d>=minimum}
    factors.difference_update(goals)
    ranked=[]
    for f in factors:
        covered=exact=0
        for t in goals:
            q,r=divmod(t,f)
            if not r and q>=2:
                exact+=1
                covered+=1
            elif (r<=2 and q>=2) or (f-r<=2 and q>=1 and t+f-r<=limit):
                covered+=1
        if covered>=2:
            ranked.append((covered,exact,f))
    ranked.sort(reverse=True)
    return ranked


def main():
    truth=json.loads(DB.with_name('shared_multiplier_lineage.json').read_text())
    output={}
    with DEFAULT_PUZZLES.open() as file:
        for p in csv.DictReader(file):
            goals=sorted(json.loads(p['targets']))
            minimum=max(10,max(json.loads(p['starting_values']))+1)
            limit=int(p['value_limit'])
            ranks=scan(goals,limit,minimum)
            cases=truth[p['id']]['big']
            real={f:a for f,a,*_ in cases['multipliers']}
            item=dict(n=len(goals),max_exact=max((s[1] for s in ranks),default=0),top=ranks[:5],
                      top5_full=any(real.get(f)==len(goals) for _,_,f in ranks[:5]),
                      top5_partial10=any(real.get(f,0)>=10 for _,_,f in ranks[:5]))
            if len(goals)==32:
                rng=random.Random(p['id']+'-gcd-null')
                intervals=bounds(goals,limit)
                item['control_hits']=[]
                item['size_cutoffs']={}
                for cutoff in (100,1000):
                    eligible=[row for row in ranks if row[2]>=cutoff]
                    item['size_cutoffs'][cutoff]=dict(
                        best_near=eligible[0][0] if eligible else 0,
                        best_exact=max((row[1] for row in eligible),default=0),
                        control_hits=[])
                for _ in range(5):
                    shifted=[rng.randint(lo,hi) for lo,hi in intervals]
                    null=scan(shifted,limit,minimum)
                    item['control_hits'].append(null[0][0] if null else 0)
                    for cutoff,stats in item['size_cutoffs'].items():
                        stats['control_hits'].append(next((s[0] for s in null if s[2]>=cutoff),0))
            output[p['id']]=item
    DB.with_name('target_multiplier_scan.json').write_text(json.dumps(output,separators=(',',':'))+'\n')


if __name__=='__main__':
    main()
