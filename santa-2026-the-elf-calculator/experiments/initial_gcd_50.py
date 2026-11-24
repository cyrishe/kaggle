#!/usr/bin/env python3
"""Fifty frozen scored puzzles: start-target GCDs and one-step arithmetic probes."""
import argparse,csv,hashlib,itertools,json,math,random,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; CUTOFFS=(10,100,1000,10000)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def options(starts,limit):
 found={v:None for v in starts}
 for a,b in itertools.combinations_with_replacement(sorted(set(starts)),2):
  plans=[(a+b,['+',a,b]),(a*b,['*',a,b])]
  if b>a:plans.append((b-a,['-',b,a]))
  if b%a==0:plans.append((b//a,['/',b,a]))
  for v,recipe in plans:
   if 0<v<=limit and v not in found:found[v]=recipe
 return found

def best_group(values,targets):
 best={str(k):None for k in CUTOFFS}
 for v,recipe in values.items():
  gcds=[math.gcd(v,t) for t in targets]
  groups={math.gcd(a,b) for a,b in itertools.combinations(gcds,2) if a>1 and b>1}
  for g in groups:
   if g<2:continue
   ts=[t for t in targets if t%g==0]
   record={'known_value':v,'known_recipe':recipe,'factor':g,'factor_is_known_value':v==g,'targets':ts,'quotients':[t//g for t in ts]}
   for k in CUTOFFS:
    old=best[str(k)]
    if g>=k and (old is None or (len(ts),g,int(v==g))>(len(old['targets']),old['factor'],int(old['factor_is_known_value']))):best[str(k)]=record
 return best

def best_exact_factor_group(values,targets):
 best={str(k):None for k in CUTOFFS}
 for v,recipe in values.items():
  ts=[t for t in targets if t%v==0 and t!=v]
  if v<10 or len(ts)<2:continue
  entry={'factor':v,'recipe':recipe,'targets':ts,'quotients':[t//v for t in ts]}
  for k in CUTOFFS:
   old=best[str(k)]
   if v>=k and (old is None or (len(ts),v)>(len(old['targets']),old['factor'])):best[str(k)]=entry
 return best

def offsets(starts,values,targets,limit,cutoff=100):
 found=[]
 for v,recipe in values.items():
  if v<cutoff:continue
  per_target=[]
  for t in targets:
   rem=t%v
   for r in sorted(set(starts)):
    if rem==r and t>r:
     per_target.append({'target':t,'offset':r,'form':'factor*quotient+offset','quotient':(t-r)//v});break
    if rem and v-rem==r and t+r<=limit:
     per_target.append({'target':t,'offset':r,'form':'factor*quotient-offset','quotient':(t+r)//v});break
  if per_target:found.append({'factor':v,'factor_recipe':recipe,'targets':per_target})
 return max(found,key=lambda x:(len(x['targets']),x['factor']),default=None),len(found)

def analyze(row):
 starts=json.loads(row['starting_values']);targets=json.loads(row['targets']);limit=int(row['value_limit']);v0={v:None for v in starts};v1=options(starts,limit)
 orig=[max(math.gcd(v,t) for v in starts) for t in targets]
 derived=[max(math.gcd(v,t) for v in v1) for t in targets]
 initial_group=best_group(v0,targets);one_group=best_group(v1,targets)
 initial_exact=best_exact_factor_group(v0,targets);one_exact=best_exact_factor_group(v1,targets)
 residual,residual_count=offsets(starts,v1,targets,limit)
 return {'id':row['id'],'starting_values':starts,'targets':targets,'value_limit':limit,'starting_gcds':orig,'one_step_gcds':derived,'initial_best_group':initial_group,'one_step_best_group':one_group,'initial_best_exact':initial_exact,'one_step_best_exact':one_exact,'offset_best':residual,'offset_factor_candidates':residual_count,'one_step_value_count':len(v1)}

def summary(cases):
 d={}
 for cutoff in CUTOFFS:
  all_n=some_n=none_n=0;one_all=one_some=one_none=0;group0=group1=exact0=exact1=0
  for c in cases:
   k=sum(g>=cutoff for g in c['starting_gcds']);k1=sum(g>=cutoff for g in c['one_step_gcds']);n=len(c['targets'])
   if k==n:all_n+=1
   elif k:some_n+=1
   else:none_n+=1
   if k1==n:one_all+=1
   elif k1:one_some+=1
   else:one_none+=1
   group0+=int(c['initial_best_group'][str(cutoff)] is not None)
   group1+=int(c['one_step_best_group'][str(cutoff)] is not None)
   exact0+=int(c['initial_best_exact'][str(cutoff)] is not None)
   exact1+=int(c['one_step_best_exact'][str(cutoff)] is not None)
  d[str(cutoff)]={'initial_all':all_n,'initial_some':some_n,'initial_none':none_n,'one_step_all':one_all,'one_step_some':one_some,'one_step_none':one_none,'initial_any':all_n+some_n,'one_step_any':one_all+one_some,'initial_shared':group0,'one_step_shared':group1,'initial_known_exact_shared':exact0,'one_step_known_exact_shared':exact1,'targets_initial':sum(sum(x>=cutoff for x in c['starting_gcds']) for c in cases),'targets_one_step':sum(sum(x>=cutoff for x in c['one_step_gcds']) for c in cases),'initial_none_to_one_step_any':sum(max(c['starting_gcds'])<cutoff and max(c['one_step_gcds'])>=cutoff for c in cases)}
 return d

def main():
 p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20261124);p.add_argument('--sample',type=int,default=50);p.add_argument('--output',type=Path,default=ROOT/'experiments/initial_gcd_50_results.json');args=p.parse_args();path=ROOT/'data/puzzles.csv'
 with path.open(newline='') as f:rows={r['id']:r for r in csv.DictReader(f)}
 ids=sorted(random.Random(args.seed).sample(sorted(rows),args.sample));cases=[analyze(rows[i]) for i in ids];summary_data=summary(cases)
 report={'seed':args.seed,'sample_size':args.sample,'sampling':'uniform random sample without replacement of sorted IDs','puzzles_sha256':sha(path),'thresholds':list(CUTOFFS),'definitions':{'initial_gcd':'max gcd(start, target), includes gcd equal to a starting or target value','one_step_gcd':'max gcd(target, initial or any single legal arithmetic result of two initial values)','group':'common divisor of a single known value and at least two targets; max over groups by coverage, then divisor; factor need not itself be in a register','offset':'target=known*quotient +/- a nonzero initial value, requiring the product to satisfy value_limit; quotient construction cost uncounted'},'total_targets':sum(len(c['targets']) for c in cases),'summary':summary_data,'cases':cases}
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('IDs',*ids);print('targets',report['total_targets']);print(json.dumps(summary_data,indent=2));
 for c in cases:
  if max(c['starting_gcds'])<100:print('NO INITIAL >=100',c['id'],'starts',c['starting_values'],'gcd_max',max(c['starting_gcds']),'one_step_max',max(c['one_step_gcds']),'group',c['one_step_best_exact']['100'],'offset',c['offset_best'])
if __name__=='__main__':main()
