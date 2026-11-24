#!/usr/bin/env python3
"""One-step shared-divisor synthesis; bounded search on a frozen sample."""
import argparse,csv,itertools,json,math,sys,time,hashlib
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]

def divisors_for_pair(g, factors):
    ds=[1]
    for p in factors:
        p=int(p);e=0
        while g%p==0:g//=p;e+=1
        if e:
            old=ds[:]
            for k in range(1,e+1):ds += [v*p**k for v in old]
    if g!=1:raise ValueError('factorization incomplete')
    return ds

def synthesize(p,program,all_factors,cap):
    from graph import active_graph,first_recipes,compile_graph
    from elf import check
    graph=active_graph(p,first_recipes(p,program));vals=list(dict.fromkeys((*p.seeds,*graph)));positions={v:i for i,v in enumerate(vals)};recipes=defaultdict(list);limit=p.limit
    def add(v,r):
        if 0<v<=limit and v not in graph and v not in p.seeds and v not in r[1:] and len(recipes[v])<16:recipes[v].append(r)
    for i,a in enumerate(vals):
        for b in vals[:i+1]:
            add(a+b,('+',a,b));add(a*b,('*',a,b))
            if a!=b:add(abs(a-b),('-',max(a,b),min(a,b)))
            hi,lo=max(a,b),min(a,b)
            if hi%lo==0:add(hi//lo,('/',hi,lo))
    factors=defaultdict(set)
    for a,b in itertools.combinations((t for t in p.targets if t in graph),2):
        g=math.gcd(a,b)
        if g<2:continue
        for d in divisors_for_pair(g,all_factors[a]):
            if d>1: factors[d].update((a,b))
    allowed=set(vals)|set(recipes)
    candidates=[]
    for f,targets in factors.items():
        if f not in allowed:continue
        ok=[t for t in sorted(targets) if f!=t and t//f in allowed and t//f!=t]
        if len(ok)>=2:candidates.append((len(ok),f,ok))
    candidates.sort(key=lambda x:(-x[0],-x[1]))
    counts={'factor_candidates':len(factors),'reachable_factor_groups':len(candidates),'tested':0,'invalid_cycle':0,'shorter_graphs':0,'valid_improvements':0};best=program;best_info=None
    for _,f,targets in candidates[:cap]:
        groups=[targets]+[list(pair) for pair in itertools.combinations(targets[:8],2)]
        for group in groups:
            proposed=graph.copy()
            boundary=min(positions[t] for t in group)
            def earlier(value, deadline):
                if value in positions:return positions[value]<deadline
                for recipe in recipes.get(value,()):
                    if max(positions[recipe[1]],positions[recipe[2]])<deadline:
                        proposed[value]=recipe;return True
                return False
            if not earlier(f,boundary):continue
            possible=True
            for t in group:
                q=t//f
                if not earlier(q,positions[t]):possible=False;break
                proposed[t]=('*',f,q)
            if not possible:continue
            counts['tested']+=1
            try:draft=active_graph(p,proposed)
            except (ValueError,KeyError):counts['invalid_cycle']+=1;continue
            if len(draft)>=len(best):continue
            counts['shorter_graphs']+=1
            tape=compile_graph(p,draft,attempts=4,recompute=True,schedule_width=4)
            if tape is None or len(tape)>=len(best):continue
            check(p,tape);best=tape;counts['valid_improvements']+=1;best_info={'factor':f,'targets':group,'quotients':[t//f for t in group],'graph_nodes':len(draft)}
    return best,counts,best_info

def main():
    a=argparse.ArgumentParser();a.add_argument('--repo',type=Path,default=ROOT/'external/hansen_repository');a.add_argument('--puzzles',type=Path,default=ROOT/'data/puzzles.csv');a.add_argument('--baseline',type=Path,default=ROOT/'external/asterios_v196/merged_132477.csv');a.add_argument('--factors',type=Path,default=ROOT/'experiments/factor_12_cases.json');a.add_argument('--cap',type=int,default=1000);a.add_argument('--out',type=Path,default=ROOT/'experiments/pilot_factor_joint');args=a.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from elf import read_puzzles,read_submission,write_submission
    puzzles={p.id:p for p in read_puzzles(args.puzzles)};base=read_submission(args.baseline);raw=json.loads(args.factors.read_text());output={};rows=[]
    for case in raw['cases']:
        ident=case['id'];p=puzzles[ident];start=time.monotonic();fs={int(t['target']):t['factors'] for t in case['targets']};tape,counts,info=synthesize(p,base[ident],fs,args.cap);output[ident]=tape;row={'id':ident,'before':len(base[ident]),'after':len(tape),'stats':counts,'win':info,'seconds':round(time.monotonic()-start,2)};rows.append(row);print(json.dumps(row),flush=True)
    args.out.mkdir(parents=True,exist_ok=True);write_submission(args.out/'wins.csv',[puzzles[i] for i in output],output);(args.out/'report.json').write_text(json.dumps({'baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),'factors_sha256':hashlib.sha256(args.factors.read_bytes()).hexdigest(),'factor_group_cap':args.cap,'rows':rows},indent=2)+'\n')
if __name__=='__main__':main()
