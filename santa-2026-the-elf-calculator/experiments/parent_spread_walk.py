"""Compare 400 independent F3 starts with stratified sampling of exact-depth-two parents."""
import argparse
import csv
import gzip
import json
import random
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from bisect import bisect_left

from independent_f3_walk import (CASES, SEED, ROOT, DEFAULT_PUZZLES, Construction, Layer,
                                 run_path, build_layer, local_repair, shared_helper_repair, validate)


@dataclass(frozen=True)
class Opening:
    value: int
    parents: tuple
    prefixes: tuple
    unit: bool
    small: bool


def candidate_pool(layer, rng):
    depth = {}
    for v, rule in layer.shallow.items():
        depth[v] = 0 if rule is None else 1+max(depth[rule[1]],depth[rule[2]])
    buckets = []
    for bits in range(1,int(layer.keys[-1]).bit_length()+1):
        lo = bisect_left(layer.keys,1<<(bits-1))
        hi = bisect_left(layer.keys,1<<bits)
        group = []
        # Same draws as the earlier 200-start run, so that its control can be extended.
        for j in rng.sample(range(lo,hi),min(hi-lo,600)):
            v = layer.keys[j]
            if v in depth:
                continue
            seq = layer.recipe(v)
            op,a,b,_ = seq[-1]
            parents = tuple(sorted({n for n in (a,b) if depth[n]==2}))
            assert parents
            small,large = sorted((a,b))
            unit = op in '+-' and small==1
            near = unit or (op in '+-' and 100*small<=large)
            group.append(Opening(v,parents,(seq[:1],seq[:2],seq[:3]),unit,near))
        if group:
            buckets.append(group)
    return buckets, sum(d==2 for d in depth.values())


class Usage:
    def __init__(self):
        self.parents = Counter()
        self.prefixes = Counter()

    def add(self, item):
        self.parents.update(item.parents)
        self.prefixes.update(item.prefixes)

    def score(self,item,spread=True):
        prefix_cost = tuple(self.prefixes[p] for p in item.prefixes)
        if not spread:
            return prefix_cost
        loads = [self.parents[n] for n in item.parents]
        return (-loads.count(0),max(loads),sum(loads)) + prefix_cost


def choose(pool,rng,count,spread):
    buckets = [list(g) for g in pool]
    usage = Usage()
    selected = []
    while buckets and len(selected)<count:
        rng.shuffle(buckets)
        for group in buckets:
            idx = min(range(len(group)),key=lambda i:usage.score(group[i],spread))
            item = group.pop(idx)
            usage.add(item)
            selected.append(item)
            if len(selected)==count:
                break
        buckets = [g for g in buckets if g]
    if len(selected)!=count:
        raise ValueError('Too few eligible openings')
    return selected


def replace_simple(pool,original,flag):
    """Keep every approved opening in place; replace only the rejected entries."""
    keep = {e.value for e in original if not getattr(e,flag)}
    usage = Usage()
    for e in original:
        if e.value in keep:
            usage.add(e)
    buckets = {g[0].value.bit_length():[x for x in g if x.value not in keep and not getattr(x,flag)]
               for g in pool}
    new = []
    for e in original:
        if not getattr(e,flag):
            new.append(e)
            continue
        bits = e.value.bit_length()
        group = min((b for b in buckets if buckets[b]),key=lambda b:(abs(b-bits),b))
        choices = buckets[group]
        index = min(range(len(choices)),key=lambda idx:usage.score(choices[idx]))
        item = choices.pop(index)
        usage.add(item)
        new.append(item)
    return new


def experiment(args):
    p,folder = args
    rng = random.Random(SEED+int(p['id'][-4:]))
    model = Construction(p)
    layer = Layer(model,folder)
    pool,available = candidate_pool(layer,rng)
    state = rng.getstate()
    control = choose(pool,rng,400,False)
    rng.setstate(state)
    spread = choose(pool,rng,400,True)
    no_unit = replace_simple(pool,spread,'unit')
    no_small = replace_simple(pool,no_unit,'small')
    groups = dict(prefix=control,parents=spread,no_unit=no_unit,no_small=no_small)
    cache = {}
    repaired = {}
    summaries = {}
    for label,group in groups.items():
        assert len({e.value for e in group})==400
        for e in group:
            if e.value not in cache:
                row,program = run_path(model,layer,e.value,150)
                if row['status']=='complete':
                    row['program']=program
                cache[e.value]=row
        runs=[cache[e.value] for e in group]
        assert all(r['status']=='complete' or (r['steps']==150 and r['status']=='cap') for r in runs)
        full=[r for r in runs if r['status']=='complete']
        finalists=sorted(full,key=lambda r:r['steps'])[:3]
        for r in finalists:
            if r['opening'] in repaired:
                continue
            best=r['program']
            for seed in (11,29):
                prog,_=local_repair(p,r['program'],seed,budget=32,reschedule=True)
                prog,_=shared_helper_repair(p,prog,seed,rounds=5)
                validate(p,prog)
                if len(prog)<len(best):
                    best=prog
            repaired[r['opening']]=best
        loads=Counter(n for e in group for n in e.parents)
        summaries[label]=dict(seeds=[e.value for e in group],f2_used=len(loads),max_f2_load=max(loads.values()),
                              distinct_prefix3=len({e.prefixes[2] for e in group}),units=sum(e.unit for e in group),
                              simple=sum(e.small for e in group),complete=len(full),median_hits=median(r['hits'] for r in runs),
                              max_hits=max(r['hits'] for r in runs),median_length=median(r['steps'] for r in full) if full else None,
                              best=min((r['steps'] for r in full),default=None),
                              finalists=[(r['opening'],r['steps'],len(repaired[r['opening']])) for r in finalists])
        print(p['id'],label,len(loads),summaries[label]['units'],len(full),summaries[label]['best'],flush=True)
    return dict(id=p['id'],targets=len(model.targets),f2_available=available,strategies=summaries,runs=cache,repaired=repaired)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path)
    args=parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:
        puzzles={p['id']:p for p in csv.DictReader(f)}
    with tempfile.TemporaryDirectory() as tmp:
        folder=args.prepared_dir or Path(tmp)
        if not args.prepared_dir:
            binary=folder/'build'
            subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('full_third_layer.cpp')),'-o',str(binary)],check=True)
            for ident in CASES:
                build_layer(puzzles[ident],folder,binary)
        with ProcessPoolExecutor(max_workers=4) as group:
            results=list(group.map(experiment,[(puzzles[i],folder) for i in CASES]))
    with gzip.open(ROOT/'reports/parent_spread_walk_400.json.gz','wt') as f:
        json.dump(results,f,separators=(',',':'))
