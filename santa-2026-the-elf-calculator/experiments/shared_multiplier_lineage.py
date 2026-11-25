"""Measure common multipliers in first-hit instruction DAGs versus near their outputs."""
import json
import sqlite3
from collections import defaultdict
from baseline_lineage import DB


def analyze(nodes, goals, full_set, big):
    targets = {v:1<<i for i,v in enumerate(goals)}
    all_bits = (1<<len(goals))-1
    first, values, parents = {}, {}, {}
    for s,v,op,a,b in nodes:
        first.setdefault(v,s)
        values[s]=v
        if op:
            parents[s]=(op,a,b)
    needed=defaultdict(int)
    terminal=defaultdict(int)
    penultimate=defaultdict(int)
    for t,bit in targets.items():
        s=first[t]
        needed[s] |= bit
        terminal[s] |= bit
        if s in parents:
            for a in parents[s][1:]:
                penultimate[a] |= bit
    mult=defaultdict(int)
    last=defaultdict(int)
    near=defaultdict(int)
    products=defaultdict(set)
    single_product=defaultdict(int)
    for s in reversed(parents):
        op,a,b=parents[s]
        mask=needed[s]
        needed[a] |= mask
        needed[b] |= mask
        if op!='*' or not mask:
            continue
        for f in {values[a],values[b]}:
            if big(f):
                mult[f] |= mask
                last[f] |= terminal[s]
                near[f] |= terminal[s] | penultimate[s]
                products[f].add(values[s])
                single_product[f]=max(single_product[f],mask.bit_count() if hasattr(int,'bit_count') else bin(mask).count('1'))
    def count(mask):
        return bin(mask).count('1')
    def ratio_masks(masks):
        union=0
        best=0
        for f in full_set:
            m=masks.get(f,0)
            union |= m
            best=max(best,count(m))
        return [count(union),best]
    ranked=sorted(mult,key=lambda f:(-count(mult[f]),-count(near[f]),-len(products[f]),f))
    assert all(f in full_set for f,m in mult.items() if m==all_bits)
    return dict(n=len(goals),common=len(full_set),ancestry=ratio_masks(mult),
                final_two=ratio_masks(near),final_mul=ratio_masks(last),
                max_partial_near=max(map(count,near.values()),default=0),
                multipliers=[[f,count(mult[f]),count(near[f]),count(last[f]),len(products[f]),single_product[f]]
                             for f in ranked])


if __name__=='__main__':
    previous=json.loads(DB.with_name('full_coverage_helpers.json').read_text())
    cases={}
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as c:
        for h in previous['cases']:
            i=h['id']
            goals=json.loads(c.execute('SELECT targets FROM puzzles WHERE id=?',(i,)).fetchone()[0])
            nodes=c.execute('SELECT step,value,op,left_step,right_step FROM nodes WHERE puzzle=? ORDER BY step',(i,)).fetchall()
            starts={v for s,v,*_ in nodes if s<0}
            common={v['value'] for v in h['values']}
            # A target cannot be an ancestor of its own first production.
            cases[i]={'ge10':analyze(nodes,goals,common,lambda f:f>=10 and f not in starts and f not in goals),
                      'big':analyze(nodes,goals,{v for v in common if v>max(starts)},
                                    lambda f:f>=10 and f>max(starts) and f not in goals)}
    DB.with_name('shared_multiplier_lineage.json').write_text(json.dumps(cases,separators=(',',':'))+'\n')
    for label in ('ge10','big'):
        rs=[c[label] for c in cases.values()]
        for name in ('ancestry','final_two','final_mul'):
            print(label,name,sum(c['n'] for c in rs),sum(c[name][0] for c in rs),sum(c[name][0]==c['n'] for c in rs),sum(c[name][1]==c['n'] for c in rs))
        print('one shared product in all target ancestries',sum(any(f[-1]==c['n'] for f in c['multipliers']) for c in rs))
