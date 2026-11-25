"""Independent, size-stratified F3 openings followed by deterministic greedy completion."""
import argparse
import csv
import gzip
import json
import math
import mmap
import random
import subprocess
import tempfile
from bisect import bisect_left
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

from baseline_lineage import DEFAULT_PUZZLES, ROOT
from capped_path_walk import CASES, SEED
from first_solver import validate
from hybrid_graph_search import Construction, local_repair, shared_helper_repair
from sparse_depth_study import dependencies


class Layer:
    def __init__(self, model, directory):
        self.shallow = model.shallow
        support = dependencies(self.shallow)
        self.parents = sorted(support, key=lambda v:(len(support[v]),v))
        ident = model.puzzle['id']
        def load(suffix, fmt):
            with (directory/(ident+suffix)).open('rb') as f:
                return memoryview(mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)).cast(fmt)
        self.keys = load('.keys','Q')
        self.rules = load('.rules','I')
        assert len(self.keys)==len(self.rules)
        assert all(v in self.neighbors(v) for v in self.shallow)

    @lru_cache(maxsize=131072)
    def neighbors(self,n):
        idx = bisect_left(self.keys,n)
        return tuple(self.keys[max(0,idx-1):idx+1])

    @lru_cache(maxsize=65536)
    def recipe(self,n):
        ordered = {}
        def visit(x):
            if x in ordered:
                return
            if x in self.shallow:
                rule = self.shallow[x]
                if rule is None:
                    return
            else:
                idx = bisect_left(self.keys,x)
                assert idx<len(self.keys) and self.keys[idx]==x
                code = self.rules[idx]
                a,b = sorted((self.parents[code>>16],self.parents[(code>>2)&16383]),reverse=True)
                rule = ('+-*/'[code&3],a,b,x)
            visit(rule[1])
            visit(rule[2])
            ordered[x] = rule
        visit(n)
        return tuple(ordered.values())


def opening_values(layer, count, rng):
    buckets = []
    for bit in range(1,int(layer.keys[-1]).bit_length()+1):
        lo = bisect_left(layer.keys,1<<(bit-1))
        hi = bisect_left(layer.keys,1<<bit)
        sampled = rng.sample(range(lo,hi),min(hi-lo,count*3))
        candidates = []
        for j in sampled:
            v = layer.keys[j]
            if v not in layer.shallow:
                seq = layer.recipe(v)
                candidates.append((v,seq[:1],seq[:2],seq[:3]))
        if candidates:
            buckets.append(candidates)
    uses = Counter()
    seeds = []
    while buckets and len(seeds)<count:
        rng.shuffle(buckets)
        for bucket in buckets:
            idx = min(range(len(bucket)),key=lambda i:tuple(uses[p] for p in bucket[i][1:]))
            v,*prefixes = bucket.pop(idx)
            uses.update(prefixes)
            seeds.append(v)
            if len(seeds)==count:
                break
        buckets = [b for b in buckets if b]
    return seeds


def make_plan(t, layer, live, limit):
    """Commit to one term at a time, reducing absolute residual per marginal operation."""
    ready = set(live)
    plan = []
    joins = []
    n = t
    while n not in ready:
        best_rank = None
        chosen = None
        missing = {}
        def materialize(source):
            if source in ready:
                return ()
            if source not in missing:
                needed = {source}
                patch = []
                for rule in reversed(layer.recipe(source)):
                    if rule[3] in needed and rule[3] not in ready:
                        patch.append(rule)
                        needed.update(rule[1:3])
                missing[source] = tuple(reversed(patch))
            return missing[source]
        def consider(p, factor=0, partner=0):
            nonlocal best_rank,chosen
            gap = abs(n-p)
            if gap>=n or p>limit:
                return
            if p in ready:
                extra = ()
            else:
                source = partner if factor else p
                extra = materialize(source)
                if factor:
                    extra += (('*',factor,partner,p),)
            cost = len(extra)+int(gap!=0)
            gain = math.log2(n+1)-math.log2(gap+1)
            rank = (gain/max(1,cost),-gap,-cost)
            if best_rank is None or rank>best_rank:
                best_rank,chosen = rank,(p,gap,extra)
        for p in layer.neighbors(n):
            consider(p)
        available = sorted(ready)
        j = bisect_left(available,n)
        for p in available[max(0,j-1):j+1]:
            consider(p)
        for a in available:
            if a<=1 or a>=2*n:
                continue
            q = (n+a-1)//a
            j = bisect_left(available,q)
            for b in available[max(0,j-1):j+1] + list(layer.neighbors(q)):
                if b>1:
                    consider(a*b,a,b)
        p,gap,extra = chosen
        for rule in extra:
            if rule[3] not in ready:
                plan.append(rule)
                ready.add(rule[3])
        if not gap:
            break
        joins.append(('+' if p<n else '-',p,gap,n))
        n = gap
    for rule in reversed(joins):
        if rule[3] not in ready:
            plan.append(rule)
            ready.add(rule[3])
    return plan


def run_path(model, layer, opening, cap):
    starts,goals = model.starts,model.targets
    slots = {v:i for i,v in enumerate(starts)}
    remaining = set(goals)-set(starts)
    program = []
    def emit(plan):
        uses = Counter(a for rule in plan for a in rule[1:3])
        for op,a,b,v in plan:
            uses[a]-=1
            uses[b]-=1
            if not remaining:
                break
            if v in slots:
                continue
            if len(program)>=cap:
                return 'cap'
            i,j = slots[a],slots[b]
            if len(slots)<int(model.puzzle['registers']):
                dest = min(set(range(int(model.puzzle['registers'])))-set(slots.values()))
            else:
                eligible = [x for x in slots if x not in starts and not uses[x]]
                if not eligible:
                    return 'registers'
                victim=min(eligible,key=lambda x:(sum(g%x==0 for g in remaining),x<=32,-x.bit_length(),x))
                dest=slots.pop(victim)
            program.append([op,i,j,dest])
            slots[v]=dest
            remaining.discard(v)
        return None
    prefix = layer.recipe(opening) if opening is not None else ()
    status = emit(prefix)
    for t in goals:
        if status or not remaining:
            break
        if t in remaining:
            status=emit(make_plan(t,layer,slots,model.limit))
    if not remaining:
        validate(model.puzzle,program)
        status='complete'
    assert status and len(program)<=cap
    return dict(opening=opening,prefix_steps=len(prefix),status=status,
                steps=len(program),hits=len(goals)-len(remaining)),program


def run_case(args):
    p, directory, count, cap = args
    model = Construction(p)
    layer = Layer(model,directory)
    seeds = opening_values(layer,count,random.Random(SEED+int(p['id'][-4:])))
    assert len(set(seeds))==count
    rows,complete = [],[]
    for v in seeds:
        row,program = run_path(model,layer,v,cap)
        if row['status']=='complete':
            complete.append((len(program),len(rows),program))
            row['program']=program
        rows.append(row)
    finalists=[]
    for _,idx,program in sorted(complete)[:3]:
        best=program
        for seed in (11,29):
            candidate,_ = local_repair(p,program,seed,budget=32,reschedule=True)
            candidate,_ = shared_helper_repair(p,candidate,seed,rounds=5)
            if len(candidate)<len(best):
                best=candidate
        validate(p,best)
        finalists.append(dict(trial=idx,opening=rows[idx]['opening'],steps=len(program),repaired=len(best),program=best))
    summary = dict(id=p['id'],targets=len(model.targets),F3=len(layer.keys),cap=cap,trials=len(rows),
                   completed=len(complete),max_hits=max(r['hits'] for r in rows),
                   first_three=len({layer.recipe(v)[:3] for v in seeds}),first_op=len({layer.recipe(v)[:1] for v in seeds}))
    print(summary,[(f['steps'],f['repaired']) for f in finalists],flush=True)
    control,program=run_path(model,layer,None,cap)
    if control['status']=='complete':
        control['program']=program
    return dict(summary=summary,control=control,finalists=finalists,runs=rows)


def build_layer(puzzle,directory,binary):
    m=Construction(puzzle)
    deps=dependencies(m.shallow)
    keys=sorted(deps,key=lambda v:(len(deps[v]),v))
    data=f'{len(keys)} {m.limit}\n'+' '.join(map(str,keys))
    stem=puzzle['id']
    subprocess.run([str(binary),directory/(stem+'.keys'),directory/(stem+'.rules')],input=data,text=True,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',nargs='+',default=CASES)
    parser.add_argument('--trials',type=int,default=200)
    parser.add_argument('--cap',type=int,default=150)
    parser.add_argument('--prepared-dir',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/independent_f3_walk.json.gz')
    args=parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:
        puzzles={p['id']:p for p in csv.DictReader(f)}
    with tempfile.TemporaryDirectory() as tmp:
        directory=args.prepared_dir or Path(tmp)
        if not args.prepared_dir:
            binary=directory/'build'
            subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('full_third_layer.cpp')),'-o',str(binary)],check=True)
            for ident in args.ids:
                build_layer(puzzles[ident],directory,binary)
        with ProcessPoolExecutor(max_workers=min(4,len(args.ids))) as pool:
            results=list(pool.map(run_case,[(puzzles[i],directory,args.trials,args.cap) for i in args.ids]))
    with gzip.open(args.output,'wt') as f:
        json.dump(results,f,separators=(',',':'))
