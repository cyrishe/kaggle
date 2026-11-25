"""Benchmark a bounded multi-target arithmetic hypergraph with fresh, input-only seeds."""
import argparse
import csv
import json
import math
import random
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations_with_replacement
from pathlib import Path

from baseline_lineage import ROOT, DEFAULT_PUZZLES
from benchmark_hybrid_graph import load_reference
from depth_graph_study import inverse, rules
from factor_quotient_solver import schedule
from factor_routing import exact_groups
from export_50_baseline_cases import replay
from first_solver import validate
from hybrid_graph_search import Construction, live_rollout, program_rules
from probe_baseline_pair import compile_values


def dictionary(p):
    m=Construction(p)
    starts,goals,limit=m.starts,m.targets,m.limit
    paths=[]
    for seed in (None,349,802):
        prog,_=live_rollout(m,seed,virtual=True,policy='shared' if seed==349 else 'order')
        if prog is not None:
            paths.append(program_rules(p,prog))
    groups=exact_groups(goals,max(10,max(starts)+1))
    selected=[]
    for f,r,ts in groups:
        if len(ts)>=3 and ts not in [v for _,v in selected]:
            selected.append((f,ts))
        if len(selected)==2:
            break
    for f,members in selected:
        rest=[v for v in goals if v not in members]
        proxy=dict(p,targets=json.dumps(list(dict.fromkeys([f]+[t//f for t in members]+rest))))
        prog,_=live_rollout(Construction(proxy),virtual=True)
        if prog is not None:
            lifted=schedule(p,program_rules(proxy,prog),{v:('*',f,v//f,v) for v in members},[goals])
            if lifted is not None:
                paths.append(program_rules(p,lifted))
    if not paths:
        from first_solver import build
        paths.append(program_rules(p,build(p,8)))
    mandatory=set(starts)|set(goals)|{r[3] for path in paths for r in path}
    cheap_cost={}
    for v,rule in m.shallow.items():
        cheap_cost[v]=0 if rule is None else 1+cheap_cost[rule[1]]+(0 if rule[1]==rule[2] else cheap_cost[rule[2]])
    cheap=sorted(m.shallow,key=lambda v:(cheap_cost[v],v))
    core=set(cheap[:180])|set(range(1,min(limit,96)+1))
    pivots=set(cheap[:85])|set(range(1,34))
    support=defaultdict(int)
    votes=Counter()
    def propose(v,bit,weight):
        if 0<v<=limit:
            support[v]|=bit
            votes[v]+=weight
    for ix,t in enumerate(goals):
        bit=1<<ix
        for a in pivots:
            propose(t-a,bit,1);propose(t+a,bit,1)
            if t%a==0:
                propose(t//a,bit,4)
            else:
                q,r=divmod(t,a)
                if min(r,a-r)<=2:
                    propose(q+(r>a//2),bit,1)
        root=math.isqrt(t)
        for a in (root,root+1):
            propose(a,bit,2);propose(a*a,bit,2);propose(abs(t-a*a),bit,1)
        for j,u in enumerate(goals[:ix]):
            pair=bit|1<<j
            d=t-u
            propose(d,pair,4)
            g=math.gcd(u,t)
            if g>1:
                propose(g,pair,5);propose(t//g,bit,4);propose(u//g,1<<j,4)
            q,r=divmod(t,u)
            if q>0:
                propose(q,pair,1);propose(r,pair,1)
    for f,_,members in groups[:30]:
        for t in goals:
            q,r=divmod(t,f)
            bit=1<<goals.index(t)
            for k in (q,q+1):
                if k>=1:
                    propose(k*f,bit,3);propose(k,bit,2);propose(abs(k*f-t),bit,2)
    bridge_rank=sorted(votes,key=lambda v:(-support[v].bit_count() if hasattr(int,'bit_count') else -bin(support[v]).count('1'),-votes[v],v))
    values=mandatory|core|set(cheap[:360])|set(bridge_rank[:1100])
    # For each promising bridge include a few cheap ways to factor or correct it.
    for v in bridge_rank[:110]:
        for a in range(2,33):
            if v%a==0: values.add(v//a)
        if v>1: values.add(v-1)
    return sorted(values),paths


def extend_dictionary(p,values,paths,extra_programs):
    starts=set(json.loads(p['starting_values']))
    goals=set(json.loads(p['targets']))
    limit=int(p['value_limit'])
    extra=set()
    for prog in extra_programs:
        validate(p,prog)
        path=program_rules(p,prog)
        paths.append(path)
        live=starts|{r[-1] for r in path}
        extra.update(live)
        born=defaultdict(list)
        for a,b in combinations_with_replacement(sorted(live),2):
            for op,x,y,v in rules(a,b,limit):
                if 0<v<=limit and v not in live:
                    born[v].append((x,y))
        consumers=defaultdict(set)
        for t in live-starts:
            for a in live:
                for op,x,y in inverse(t,a,limit):
                    if t in (x,y):continue
                    h=y if x==a else x
                    if h in born and any(t not in pair for pair in born[h]):
                        consumers[h].add(t)
        ranked=sorted(consumers,key=lambda h:(-len(consumers[h]),-len(consumers[h]&goals),h))
        extra.update(ranked[:250])
    return sorted(set(values)|extra),paths


def run(job):
    p,binary,trials,seed,extra_programs,catalog,marginal,*diagnostic=job
    start=time.monotonic()
    vs,paths=dictionary(p)
    if extra_programs:
        vs,paths=extend_dictionary(p,vs,paths,extra_programs)
    starts=json.loads(p['starting_values']);goals=json.loads(p['targets'])
    catalog_size=0
    if catalog:
        from short_expression_bridges import augment
        vs,catalog_size=augment(starts,goals,int(p['value_limit']),vs,paths)
    added=[]
    if diagnostic:
        # A separate counterfactual benchmark only. Numeric hints never enter a clean run.
        mode=diagnostic[0]
        reference=load_reference(p['id'])
        known=set(vs)
        extras={r[3] for r in program_rules(p,reference)}-known
        if mode=='all_values':
            added=sorted(extras)
        elif mode=='matched_noise':
            rng=random.Random('bridge-diagnostic-'+p['id'])
            limit=int(p['value_limit'])
            for v in sorted(extras):
                radius=max(25,v//100)
                lo,hi=max(1,v-radius),min(limit,v+radius)
                while True:
                    x=rng.randint(lo,hi)
                    if x not in known and x not in extras:break
                    if hi-lo<2*(len(known)+len(extras)):
                        lo=max(1,lo-radius);hi=min(limit,hi+radius)
                known.add(x);added.append(x)
        else:raise ValueError(mode)
        vs=sorted(set(vs)|set(added))
    ix={v:i for i,v in enumerate(vs)}
    lines=[f"{len(vs)} {len(starts)} {len(goals)} {p['registers']} 4096",' '.join(map(str,vs)),
           ' '.join(str(ix[x]) for x in starts),' '.join(str(ix[x]) for x in goals),str(len(paths))]
    for path in paths:
        lines.append(str(len(path)))
        lines.extend(f'{op} {ix[a]} {ix[b]} {ix[v]}' for op,a,b,v in path)
    setup=time.monotonic()-start
    cmd=[str(binary),str(trials),str(seed)]+(['grow'] if marginal else [])
    proc=subprocess.run(cmd,input='\n'.join(lines)+'\n',capture_output=True,text=True)
    if proc.returncode:
        raise RuntimeError(f"{p['id']}: {proc.stderr}")
    data=iter(proc.stdout.splitlines())
    nodes,nrules=map(int,next(data).split())
    arms={}
    for header in data:
        arm,budget,count,peak,secs,unique,*curve=header.split()
        seq=[]
        for _ in range(int(count)):
            op,a,b,v=next(data).split()
            seq.append((op,vs[int(a)],vs[int(b)],vs[int(v)]))
        prog=compile_values(p,seq,goals)
        assert validate(p,prog)[0]==int(count)
        arms[arm]=dict(steps=len(prog),peak=int(peak),seconds=float(secs),distinct=int(unique),
                       curve=list(map(int,curve)),program=prog)
    reference=load_reference(p['id'])
    validate(p,reference)
    def landmarks(prog):
        hits=[n for n,*_,mark in replay(p,prog) if mark=='★ 首次命中']
        return [hits[0],hits[(len(hits)-1)//2],hits[-1]] if hits else []
    refpath=program_rules(p,reference)
    missing=sorted({r[-1] for r in refpath}-set(vs))
    clean_registers=[True]*len(starts)+[False]*(int(p['registers'])-len(starts))
    seen=set(starts)
    complete_targets=set(starts)&set(goals)
    for (_,a,b,dest),(_,_,_,v) in zip(reference,refpath):
        clean_registers[dest]=clean_registers[a] and clean_registers[b] and v in ix
        if clean_registers[dest] and v in goals and v not in seen:
            complete_targets.add(v)
        seen.add(v)
    row=dict(goals=len(goals),seed=seed,trials=trials,nodes=nodes,rules=nrules,public=len(reference),
             inputs_only=not diagnostic,diagnostic=diagnostic or None,added=len(added),catalog_size=catalog_size,extra_source_count=len(extra_programs),source_steps=[len(x) for x in paths],setup_seconds=round(setup,3),arms=arms,
             reference_distinct=len({r[-1] for r in refpath}),reference_missing=missing,
             reference_first_hit_roots_supported=len(complete_targets),reference_hit_steps=landmarks(reference),
             own_hit_steps=landmarks(min((a['program'] for a in arms.values()),key=len)))
    print(p['id'],len(goals),nodes,nrules,[a['steps'] for a in arms.values()],len(reference),flush=True)
    return p['id'],row


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--ids',nargs='+');cli.add_argument('--trials',type=int,default=500)
    cli.add_argument('--seed',type=int,default=20261125);cli.add_argument('--workers',type=int,default=4)
    cli.add_argument('--output',type=Path,default=ROOT/'reports/joint_bridge_search.json')
    cli.add_argument('--refine',type=Path,help='Expand around programs from a preceding input-only bridge run.')
    cli.add_argument('--catalog',action='store_true',help='Backwards lookups against short arithmetic expressions.')
    cli.add_argument('--marginal',action='store_true',help='Also grow randomized solutions by marginal goal cost.')
    args=cli.parse_args()
    with DEFAULT_PUZZLES.open() as file: puzzles={p['id']:p for p in csv.DictReader(file)}
    compact=[i for i,p in puzzles.items() if 1000<max(json.loads(p['targets']))<=100000]
    named=['scored_0810','scored_0253','scored_0035','scored_0667']
    sample=random.Random(457210).sample(sorted(set(puzzles)-set(named+['scored_0307','scored_0755'])),4)
    ids=args.ids or list(dict.fromkeys(compact+named+sample))
    extras=defaultdict(list)
    if args.refine:
        prev=json.loads(args.refine.read_text())
        archived=json.loads((ROOT/'reports/monte_carlo_prefix_benchmark.json').read_text())
        for i in ids:
            options=[a['program'] for a in prev[i]['arms'].values()]
            if i in archived:
                options.extend(archived[i][k]['program'] for k in ('initial','fresh','repair') if archived[i][k]['program'])
            for prog in sorted(options,key=len):
                if prog not in extras[i] and len(extras[i])<3:extras[i].append(prog)
    with tempfile.TemporaryDirectory() as folder:
        binary=Path(folder)/'joint-search'
        subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('joint_bridge_search.cpp')),'-o',str(binary)],check=True)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            out=dict(pool.map(run,[(puzzles[i],binary,args.trials,args.seed,extras[i],args.catalog,args.marginal) for i in ids]))
    args.output.write_text(json.dumps(out,separators=(',',':'))+'\n')


if __name__=='__main__':
    main()
