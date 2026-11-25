"""Measure fifth-layer storage lower bounds using legal intervals of values."""
import csv
import json
import random
import statistics
import subprocess
import tempfile
from pathlib import Path

from depth_graph_study import ROOT, DEFAULT_PUZZLES, shallow, rules
from itertools import combinations_with_replacement


def restricted_join(puzzle):
    """Reverse two steps per goal, with one depth-1-or-earlier operand per step."""
    starts = json.loads(puzzle['starting_values'])
    goals = json.loads(puzzle['targets'])
    limit = int(puzzle['value_limit'])
    anchors, _ = shallow(starts, limit, 1)
    forward, _ = shallow(starts, limit, 3)
    reverse_union = set()
    connected = 0
    for goal in goals:
        frontier = {goal}
        seen = {goal}
        for _ in range(2):
            candidates = set()
            for target in frontier:
                for anchor in anchors:
                    for sibling in (target - anchor, target + anchor, anchor - target, target * anchor):
                        if 0 < sibling <= limit:
                            candidates.add(sibling)
                    if target % anchor == 0:
                        candidates.add(target // anchor)
                    if anchor % target == 0:
                        candidates.add(anchor // target)
            frontier = candidates - seen
            seen.update(frontier)
        reverse_union.update(seen)
        connected += not seen.isdisjoint(forward)
    return dict(forward=len(forward), reverse=len(reverse_union),
                goals=len(goals), connected=connected)


def measure(p,binary):
    starts=json.loads(p['starting_values'])
    limit=int(p['value_limit'])
    f2,counts=shallow(starts,limit,2)
    keys=sorted(f2)
    if len(keys)>410:
        # Spend the same pair budget on small and widely spaced magnitudes.
        tail=keys[205:]
        keys=keys[:205]+[tail[i*(len(tail)-1)//204] for i in range(205)]
    f3=set(f2)
    for a,b in combinations_with_replacement(keys,2):
        for _,_,_,v in rules(a,b,limit):
            if 0<v<=limit:f3.add(v)
    payload=f'{limit} {len(f3)}\n'+' '.join(map(str,sorted(f3)))
    r,bound=map(int,subprocess.check_output([str(binary)],input=payload,text=True).split())
    return dict(id=p['id'],limit=limit,f2_count=len(f2),f3_subset=len(f3),
                f3_complete=len(keys)==len(f2),f4_prefix=r,f5_lower=bound)


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as inp:
        puzzles={p['id']:p for p in csv.DictReader(inp)}
    seed=20261124
    sample=random.Random(seed).sample(sorted(puzzles),41)
    examples=['scored_0042','scored_0378','scored_0272','scored_0051','scored_0253']
    result={}
    with tempfile.TemporaryDirectory() as tmp:
        binary=Path(tmp)/'bound'
        subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_suffix('.cpp')),'-o',str(binary)],check=True)
        for ident in dict.fromkeys(examples+sample):
            row=measure(puzzles[ident],binary)
            result[ident]=row
            if ident in examples:print(row,flush=True)
    limits=sorted(int(p['value_limit']) for p in puzzles.values())
    summary=dict(seed=seed,sample_ids=sample,examples=examples,memory_unit='GiB',
                 median_limit=statistics.median(limits),dense_fit_12=sum((x+8)//8<=12*2**30 for x in limits),
                 dense_fit_6=sum((x+8)//8<=6*2**30 for x in limits),cases=result,
                 restricted_joins={i: restricted_join(puzzles[i]) for i in examples[:3]})
    (ROOT/'reports/fifth_layer_memory.json').write_text(json.dumps(summary,indent=2)+'\n')
    bounds=sorted(result[i]['f5_lower'] for i in sample)
    print('sample lower median',statistics.median(bounds),'8-byte over 12GiB',sum(x>12*2**30//8 for x in bounds))
