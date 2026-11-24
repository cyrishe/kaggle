#!/usr/bin/env python3
"""Explore one new shared arithmetic helper feeding two existing target nodes.

Uses graph reader/compiler from the pinned upstream repository; standalone logic
for candidate generation and ranking is local. See accompanying report.
"""
import argparse,csv,hashlib,json,sys,time
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def bridges(target,x,limit):
    # h -> target, via x; return (h, target_recipe).
    for h,op,a,b in ((target-x,'+',None,x),(target+x,'-',None,x),(x-target,'-',x,None)):
        if 0<h<=limit: yield h,(op,a,b)
    if target%x==0:
        h=target//x
        if h:yield h,('*',None,x)
    if target*x<=limit:yield target*x,('/',None,x)
    if x%target==0:yield x//target,('/',x,None)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--puzzles',type=Path,default=ROOT/'data/puzzles.csv');ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--ids',nargs='+',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--max-helpers',type=int,default=300);args=ap.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from elf import read_puzzles,read_submission,check,write_submission
    from graph import active_graph,first_recipes,compile_graph
    puzzles={p.id:p for p in read_puzzles(args.puzzles)};base=read_submission(args.baseline); results=[]; output={}
    for ident in args.ids:
        t0=time.monotonic();p=puzzles[ident];tape=base[ident];graph=active_graph(p,first_recipes(p,tape));values=list(dict.fromkeys((*p.seeds,*graph)));index={v:i for i,v in enumerate(values)}
        targets=[v for v in p.targets if v in graph];offers=defaultdict(dict)
        for target in targets:
            for x in values[:index[target]]:
                for h,(op,a,b) in bridges(target,x,p.limit):
                    if h in index or h in (target,x):continue
                    recipe=(op,h if a is None else a,h if b is None else b)
                    offers[h].setdefault(target,(recipe,x))
        relevant=[(h,items) for h,items in offers.items() if len(items)>=2]; relevant.sort(key=lambda q:(-len(q[1]),q[0])); counters={'bridge_values':len(relevant),'feasible_helpers':0,'graph_gains':0,'compiled_gains':0}; best=tape; win=None
        for h,items in relevant[:args.max_helpers]:
            for left in values:
                candidates=[('+',h-left),('-',left-h)]
                if h%left==0:candidates.append(('*',h//left))
                if left%h==0:candidates.append(('/',left//h))
                for op,right in candidates:
                    if right not in index or right==h:continue
                    bound=max(index[left],index[right]); applicable=[(target,recipe) for target,(recipe,x) in items.items() if index[target]>max(bound,index[x])]
                    if len(applicable)<2:continue
                    counters['feasible_helpers']+=1
                    # Include all, then pairs: a high-fanout helper can also help a subset.
                    options=[applicable]+[[applicable[i],applicable[j]] for i in range(min(len(applicable),8)) for j in range(i+1,min(len(applicable),8))]
                    for opt in options:
                        proposed=graph.copy();proposed[h]=(op,left,right)
                        for target,recipe in opt:proposed[target]=recipe
                        try: draft=active_graph(p,proposed)
                        except (ValueError,KeyError):continue
                        if len(draft)>=len(best):continue
                        counters['graph_gains']+=1
                        candidate=compile_graph(p,draft,attempts=4,recompute=True)
                        if candidate is not None and len(candidate)<len(best):
                            check(p,candidate);best=candidate;counters['compiled_gains']+=1;win={'helper':h,'helper_recipe':[op,left,right],'targets':[x[0] for x in opt],'graph_nodes':len(draft)}
                    break
                else: continue
                break
        output[ident]=best;results.append({'id':ident,'before':len(tape),'after':len(best),'stats':counters,'win':win,'seconds':round(time.monotonic()-t0,3)});print(json.dumps(results[-1]),flush=True)
    args.out.mkdir(parents=True,exist_ok=True);write_submission(args.out/'wins.csv',[puzzles[i] for i in args.ids],output)
    (args.out/'report.json').write_text(json.dumps({'repo_revision':'0652a700782bf452d35255b9b4993f547412cfcc','baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),'results':results,'max_helpers':args.max_helpers},indent=2)+'\n')
if __name__=='__main__':main()
