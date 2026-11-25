"""Random destroy/repair with CP-SAT confined to small, generated arithmetic neighborhoods."""
import argparse
import csv
import json
import math
import random
import time
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations_with_replacement
from pathlib import Path
from ortools.sat.python import cp_model

from baseline_lineage import ROOT, DEFAULT_PUZZLES
from depth_graph_study import inverse, rules
from hybrid_graph_search import program_rules, rooted_rules, compile_changes
from first_solver import validate


def forward(values,limit):
    recipes=defaultdict(list)
    for a,b in combinations_with_replacement(sorted(values),2):
        for op,x,y,v in rules(a,b,limit):
            if 0<v<=limit and v!=x and v!=y:
                recipes[v].append((op,x,y,v))
    return recipes


def propose(starts,goals,graph,donors,limit,rng,iteration):
    have=set(starts)|graph.keys()
    new=forward(have,limit)
    influence=defaultdict(set)
    for t in graph:
        for a in have:
            for op,x,y in inverse(t,a,limit):
                if t in (x,y):
                    continue
                h=y if x==a else x
                if h in new and h not in have and any(t not in step[1:3] for step in new[h]):
                    influence[h].add(t)
    # Retire a cluster around one or more candidate shared values. Old recipes
    # independent of the cluster can stay fixed, even while all targets remain mandatory.
    candidates=list(sorted(influence))
    ranked=sorted(candidates,key=lambda h:-math.log(max(rng.random(),1e-12)) /
                  ((len(influence[h])+0.25*sum(t in goals for t in influence[h]))**2))
    helpers=set(ranked[:rng.randrange(12,36)])
    old=set(graph)-set(goals)
    if not old:
        return have,set(),set()
    pivot=rng.choice(sorted(old))
    nearby={pivot}
    for r in graph.values():
        if r[3]==pivot or pivot in r[1:3]:
            nearby.update(r[1:])
    for h in ranked[:2]:
        for t in influence[h]:
            nearby.update(graph[t][1:3])
    cut=(old & nearby) | set(rng.sample(sorted(old),min(len(old),rng.randint(3,9))))
    if iteration%5==0:cut=old
    rewriting=cut|{v for v,r in graph.items() if cut.intersection(r[1:3])}
    # Sometimes add a complete alternative path for one target.
    if donors and iteration%3==0:
        donor=rng.choice(donors)
        t=rng.choice(sorted(goals))
        helpers.update(r[-1] for r in rooted_rules(starts,[t],donor))
    return have|helpers,cut,rewriting


def repair(p,starts,goals,graph,numbers,cut,rewriting,budget,rng):
    limit=int(p['value_limit'])
    all_rules=forward(numbers,limit)
    model=cp_model.CpModel()
    use={v:model.NewBoolVar('') for v in sorted(numbers-set(starts))}
    rank={v:model.NewIntVar(0,len(graph),'') for v in use}
    bound=len(graph)-1
    model.Add(sum(use.values())<=bound)
    choose={}
    for v in sorted(use):
        if v in goals or (v in graph and v not in cut):
            model.Add(use[v]==1)
        selected=[]
        opts=all_rules.get(v,()) if v not in graph or v in rewriting else [graph[v]]
        for rule in opts:
            op,a,b,_=rule
            pick=model.NewBoolVar('')
            choose[pick.Index()]=(pick,rule)
            selected.append(pick)
            for x in {a,b}-starts:
                model.AddImplication(pick,use[x])
                model.Add(rank[v]>rank[x]).OnlyEnforceIf(pick)
        model.Add(sum(selected)==use[v])
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=rng.randrange(1,2**30)
    solver.parameters.max_deterministic_time=budget
    solver.parameters.max_time_in_seconds=max(1.5,10*budget)
    status=solver.Solve(model)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return None,solver.StatusName(status)
    chosen={v:(op,a,b,v) for pick,(op,a,b,v) in choose.values() if solver.Value(pick)}
    seq=rooted_rules(starts,goals,chosen)
    prog=compile_changes(p,seq,goals)
    if prog is None:
        return None,'REGISTERS'
    assert validate(p,prog)[0]<=bound
    return prog,'FOUND'


def run(job):
    p,arms,rounds,seed,budget=job
    started=time.monotonic()
    starts=set(json.loads(p['starting_values']));goals=sorted(json.loads(p['targets']))
    make_graph=lambda prog:{r[-1]:r for r in program_rules(p,prog) if r[-1] not in starts}
    donors=[make_graph(a['program']) for a in arms.values()]
    best=min((a['program'] for a in arms.values()),key=len)
    before=len(best)
    history=[]
    status=Counter()
    rng=random.Random(seed+int(p['id'][-4:]))
    for ix in range(rounds):
        graph=make_graph(best)
        numbers,cut,rewriting=propose(starts,set(goals),graph,donors,int(p['value_limit']),rng,ix)
        if not cut:break
        prog,why=repair(p,starts,goals,graph,numbers,cut,rewriting,budget,rng)
        status[why]+=1
        if prog is not None and len(prog)<len(best):
            history.append(dict(trial=ix+1,before=len(best),after=len(prog)))
            donors.append(graph)
            best=prog
    matches=validate(p,best)
    print(p['id'],before,len(best),history,flush=True)
    return p['id'],dict(start=before,steps=matches[0],program=best,history=history,status=status,
                        seconds=round(time.monotonic()-started,3))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'reports/joint_bridge_search.json')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/joint_bridge_neighborhood.json')
    parser.add_argument('--rounds',type=int,default=40)
    parser.add_argument('--seed',type=int,default=91379)
    parser.add_argument('--budget',type=float,default=0.08)
    parser.add_argument('--ids',nargs='+')
    args=parser.parse_args()
    src=json.loads(args.source.read_text())
    with DEFAULT_PUZZLES.open() as file:puzzles={r['id']:r for r in csv.DictReader(file)}
    ids=args.ids or [i for i in src if max(json.loads(puzzles[i]['targets']))<=100000 or i=='scored_0810']
    with ProcessPoolExecutor(max_workers=4) as pool:
        out=dict(pool.map(run,[(puzzles[i],src[i]['arms'],args.rounds,args.seed,args.budget) for i in ids]))
    args.output.write_text(json.dumps(out,separators=(',',':'))+'\n')
