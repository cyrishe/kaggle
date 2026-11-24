#!/usr/bin/env python3
"""Bounded multi-graph beam search: replace targets by products +/- known values.

Reads and compiles the original third-party graph via the pinned Hansen repo.
This is a full-graph repair pilot, not a proof of optimality.
"""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def fingerprint(graph):
 def canonical(v,r):
  op,a,b=r
  if op in '+*' and a>b:a,b=b,a
  return v,op,a,b
 return frozenset(canonical(v,r) for v,r in graph.items())

def generate(target,p,graph,limit):
 vals=sorted(set(p.seeds)|set(graph));vset=set(vals);new_factors={}
 def add(v,op,a,b):
  if 0<v<=p.limit and v not in vset and v not in (a,b):new_factors.setdefault(v,(op,a,b))
 for i,a in enumerate(vals):
  for b in vals[:i+1]:
   add(a+b,'+',a,b);add(a*b,'*',a,b)
   if a!=b:add(a-b,'-',a,b)
   if a%b==0:add(a//b,'/',a,b)
 factor_values=sorted(vset|set(new_factors));fset=set(factor_values);seen=set();proposals=[]
 options=[(target,None,None)]
 for r in vals:
  if r==target:continue
  if target>r:options.append((target-r,'+',r))
  if target+r<=p.limit:options.append((target+r,'-',r))
 for product,op,r in options:
  if product<1 or product>p.limit or product==r:continue
  for x in factor_values:
   if x==target or product%x:continue
   y=product//x
   if y not in fset or y==target or x>y:continue
   helpers=[]
   if product==target:
    for z in (x,y):
     if z in new_factors and all(h[0]!=z for h in helpers):helpers.append((z,new_factors[z]))
    recipe=('*',x,y)
   else:
    if product not in vset:
     for z in (x,y):
      if z in new_factors and all(h[0]!=z for h in helpers):helpers.append((z,new_factors[z]))
     helpers.append((product,('*',x,y)))
    recipe=(op,product,r)
   if recipe==graph.get(target) and not helpers:continue
   key=(recipe,tuple(helpers))
   if key in seen:continue
   seen.add(key)
   priority=(len(helpers),abs(product-target),product,x,y)
   proposals.append((priority,recipe,tuple(helpers)))
 proposals.sort(key=lambda x:x[0])
 return proposals[:limit],len(proposals)

def select(candidates,width,slack):
 # Preserve best graph then prefer different value/recipe sets while near its cost.
 candidates.sort(key=lambda item:(len(item[0]),tuple(sorted(fingerprint(item[0])))))
 selected=[candidates[0]];floor=len(candidates[0][0]);pool=[item for item in candidates[1:] if len(item[0])<=floor+slack]
 while pool and len(selected)<width:
  def rank(item):
   fp=fingerprint(item[0]);novel=min(len(fp.symmetric_difference(fingerprint(x[0]))) for x in selected)
   return (novel,-len(item[0]),tuple(sorted(fp)))
  chosen=max(pool,key=rank);selected.append(chosen);pool.remove(chosen)
 return selected

def optimize(p,tape,width,slack,per_target):
 from graph import active_graph,first_recipes,compile_graph
 from elf import replay,check
 original=active_graph(p,first_recipes(p,tape)); targets=[]
 for s in replay(p,tape):
  if s.output in p.targets and s.output not in targets and s.output not in p.seeds:targets.append(s.output)
 beam=[(original,[])];counts={'targets':len(targets),'generated':0,'examined':0,'cycle_or_missing':0,'distinct_graphs':0,'max_retained':1,'nonbaseline_graphs_final':0,'compiled':0}
 stages=[]
 for target in targets:
  pool={fingerprint(g):(g,h) for g,h in beam}
  for graph,history in beam:
   if target not in graph:continue
   proposals,total=generate(target,p,graph,per_target);counts['generated']+=total
   for _,recipe,helpers in proposals:
    counts['examined']+=1;draft=graph.copy()
    conflict=False
    for value,edge in helpers:
     if value in draft or value in p.seeds:conflict=True;break
     draft[value]=edge
    if conflict:continue
    draft[target]=recipe
    try:g=active_graph(p,draft)
    except (ValueError,KeyError):counts['cycle_or_missing']+=1;continue
    fp=fingerprint(g)
    if fp not in pool:pool[fp]=(g,history+[{'target':target,'recipe':recipe,'helpers':helpers}])
  candidates=list(pool.values());counts['distinct_graphs']+=len(candidates);beam=select(candidates,width,slack);counts['max_retained']=max(counts['max_retained'],len(beam))
  stages.append({'target':target,'candidates':len(candidates),'retained':len(beam),'sizes':[len(g) for g,_ in beam]})
 best=tape;best_history=[];viable=[]
 for graph,history in beam:
  if fingerprint(graph)!=fingerprint(original):counts['nonbaseline_graphs_final']+=1
  tape2=compile_graph(p,graph,attempts=4,recompute=True,schedule_width=4)
  if tape2 is None:continue
  counts['compiled']+=1;check(p,tape2);viable.append({'graph_nodes':len(graph),'physical_steps':len(tape2),'changed_targets':len(history),'target_recipes':{str(t):graph[t] for t in p.targets if t in graph},'change_history':history,'program':tape2})
  if len(tape2)<len(best):best=tape2;best_history=history
 return best,counts,stages,viable,best_history

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=ROOT/'external/hansen_repository');ap.add_argument('--puzzles',type=Path,default=ROOT/'data/puzzles.csv');ap.add_argument('--baseline',type=Path,default=ROOT/'external/asterios_v196/merged_132477.csv');ap.add_argument('--ids',nargs='+',default=['scored_0901','scored_0810','scored_0654','scored_0556']);ap.add_argument('--width',type=int,default=5);ap.add_argument('--slack',type=int,default=2);ap.add_argument('--per-target',type=int,default=300);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
 if args.width<1 or args.per_target<1 or args.slack<0:ap.error('invalid search budget')
 sys.path.insert(0,str(args.repo.resolve()))
 from elf import read_puzzles,read_submission,write_submission,check
 puzzles={p.id:p for p in read_puzzles(args.puzzles)};base=read_submission(args.baseline);output={};rows=[]
 for ident in args.ids:
  start=time.monotonic();p=puzzles[ident];program,counts,stages,viable,history=optimize(p,base[ident],args.width,args.slack,args.per_target);check(p,program);output[ident]=program
  row={'id':ident,'before':len(base[ident]),'after':len(program),'counts':counts,'stages':stages,'final_compiled_candidates':viable,'winning_changes':history,'elapsed_seconds':round(time.monotonic()-start,3)};rows.append(row)
  print(json.dumps({k:row[k] for k in ('id','before','after','counts','elapsed_seconds')}),flush=True)
 args.out.mkdir(parents=True,exist_ok=True);write_submission(args.out/'wins.csv',[puzzles[i] for i in output],output)
 report={'puzzles_sha256':hashlib.sha256(args.puzzles.read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),'repo_revision':'0652a700782bf452d35255b9b4993f547412cfcc','width':args.width,'slack':args.slack,'per_target':args.per_target,'rows':rows}
 (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
