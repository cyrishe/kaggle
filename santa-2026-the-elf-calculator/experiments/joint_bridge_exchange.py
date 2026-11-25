"""Destroy old helpers first, then find an exact replacement shared by the entire remaining DAG."""
import argparse
import csv
import json
import math
import random
import time
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations_with_replacement
from pathlib import Path

from baseline_lineage import ROOT,DEFAULT_PUZZLES
from depth_graph_study import rules,inverse
from first_solver import validate
from hybrid_graph_search import compile_changes,program_rules,rooted_rules


class Neighbors:
    def __init__(self,p,program):
        self.p=p
        self.starts=set(json.loads(p['starting_values']))
        self.goals=set(json.loads(p['targets']))
        self.limit=int(p['value_limit'])
        graph={r[-1]:r for r in program_rules(p,program)}
        self.values=sorted(self.starts|graph.keys())
        self.bit={v:1<<i for i,v in enumerate(self.values)}
        self.initial=sum(self.bit[v] for v in self.starts)
        self.wanted=sum(self.bit[v] for v in self.goals)
        self.all=(1<<len(self.values))-1
        self.helpers=sorted(set(graph)-self.goals-self.starts)
        self.near=defaultdict(set)
        for op,a,b,v in graph.values():
            for x in (a,b):
                self.near[v].add(x);self.near[x].add(v)
        self.old=[]
        born=defaultdict(list)
        for a,b in combinations_with_replacement(self.values,2):
            for op,x,y,v in rules(a,b,self.limit):
                if v<=0 or v>self.limit or v in (x,y) or v in self.starts:continue
                inputs=self.bit[x]|self.bit[y]
                rule=(op,x,y,v)
                if v in self.bit:
                    self.old.append((inputs,self.bit[v],rule))
                else:
                    born[v].append((inputs,rule))
        # Every outside value reachable by one op and every way it can feed an
        # existing output. Includes the case where it supplies both operands.
        self.repair=defaultdict(list)
        self.born=born
        self.newbit=1<<len(self.values)
        for v in self.values:
            if v in self.starts:continue
            seen=set()
            for a in self.values:
                for op,x,y in inverse(v,a,self.limit):
                    h=y if x==a else x
                    if h not in born or v in (x,y):continue
                    rule=(op,x,y,v)
                    if rule not in seen:
                        self.repair[h].append((self.newbit|self.bit[a],self.bit[v],rule));seen.add(rule)
            for h,op in ((v//2,'+'),(math.isqrt(v),'*')):
                if h in born and (h+h if op=='+' else h*h)==v:
                    self.repair[h].append((self.newbit,self.bit[v],(op,h,h,v)))
        self.sorted_repairs=sorted(self.repair,key=lambda h:-len(self.repair[h]))

    def close(self,known,allowed,edges,book):
        while True:
            old=known
            for inputs,out,rule in edges:
                if out&allowed and not out&known and not inputs&~known:
                    known|=out
                    book[rule[-1]]=rule
            if known==old or known&self.wanted==self.wanted:return known

    def solve(self,cut,rng):
        permitted=self.all^sum(self.bit[v] for v in cut)
        base={}
        reached=self.close(self.initial,permitted,self.old,base)
        def emit(graph):
            seq=rooted_rules(self.starts,sorted(self.goals),graph)
            return compile_changes(self.p,seq,sorted(self.goals))
        if reached&self.wanted==self.wanted:
            return emit(base)
        missing=permitted&~reached
        choices=[]
        for h in self.sorted_repairs:
            gain=0
            for inputs,out,_ in self.repair[h]:
                if out&missing and not inputs&~(reached|self.newbit):gain|=out
            if not gain or not any(not inputs&~reached for inputs,_ in self.born[h]):continue
            choices.append((rng.random()-bin(gain).count('1'),h))
        for _,h in sorted(choices):
            graph=base.copy()
            graph[h]=next(rule for inputs,rule in self.born[h] if not inputs&~reached)
            edges=self.repair[h]+self.old
            got=self.close(reached|self.newbit,permitted,edges,graph)
            if got&self.wanted==self.wanted:
                trial=emit(graph)
                if trial is not None:return trial
        return None


def run(job):
    puzzle,programs,rounds,seed=job
    rng=random.Random(seed+int(puzzle['id'][-4:]))
    best=min(programs,key=len)
    initial=len(best)
    elite=[best]
    cache={}
    seen=set(); history=[];successful=0
    current=best
    start=time.monotonic()
    for i in range(rounds):
        if i%30==0:current=rng.choice(elite)
        key=tuple(sorted(r[3] for r in program_rules(puzzle,current)))
        if key not in cache:
            if len(cache)>24:cache.clear()
            cache[key]=Neighbors(puzzle,current)
        model=cache[key]
        if not model.helpers:break
        count=min(len(model.helpers),rng.choices([1,2,3,4,5],weights=[2,6,4,2,1])[0])
        pivot=rng.choice(model.helpers)
        cut={pivot}
        while len(cut)<count:
            near=set().union(*(model.near[x] for x in cut))
            candidates=sorted((near&set(model.helpers))-cut)
            if not candidates or rng.random()<0.3:candidates=sorted(set(model.helpers)-cut)
            cut.add(rng.choice(candidates))
        ck=(key,tuple(sorted(cut)))
        if ck in seen:continue
        seen.add(ck)
        trial=model.solve(cut,rng)
        if trial is None or len(trial)>len(current):continue
        newkey=tuple(sorted(r[3] for r in program_rules(puzzle,trial)))
        if newkey==key:continue
        successful+=1
        current=trial
        if len(trial)<len(best):
            history.append(dict(trial=i+1,before=len(best),after=len(trial),cut=sorted(cut)))
            best=trial
        if len(trial)<=len(best)+1:
            elite.append(trial)
            elite.sort(key=len)
            if len(elite)>8:elite.pop(rng.randrange(1,len(elite)))
    validate(puzzle,best)
    print(puzzle['id'],initial,len(best),history,flush=True)
    return puzzle['id'],dict(start=initial,steps=len(best),program=best,seed=seed,rounds=rounds,
                              distinct_cuts=len(seen),accepted=successful,history=history,seconds=round(time.monotonic()-start,3))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--ids',nargs='+')
    parser.add_argument('--rounds',type=int,default=1000);parser.add_argument('--seed',type=int,default=1347)
    args=parser.parse_args()
    with DEFAULT_PUZZLES.open() as file:puzzles={p['id']:p for p in csv.DictReader(file)}
    programs=defaultdict(list)
    for file in args.sources:
        for i,r in json.loads(file.read_text()).items():
            if 'arms' in r:programs[i].extend(a['program'] for a in r['arms'].values())
            else:programs[i].append(r['program'])
    ids=args.ids or [i for i in programs if len(min(programs[i],key=len))<=50]
    with ProcessPoolExecutor(max_workers=4) as pool:
        out=dict(pool.map(run,[(puzzles[i],programs[i],args.rounds,args.seed) for i in ids]))
    args.output.write_text(json.dumps(out,separators=(',',':'))+'\n')
