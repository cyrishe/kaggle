#!/usr/bin/env python3
"""Random-sample target/live-register GCDs with no future-state leakage."""
import argparse,csv,hashlib,json,math,random,statistics,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from first_solver import validate
csv.field_size_limit(1_000_000)
THRESHOLDS=(10,100,1000,10000)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def calc(op,a,b):
 if op=='+':return a+b
 if op=='-':return a-b
 if op=='*':return a*b
 if op=='/' and b and a%b==0:return a//b
 raise ValueError('invalid operation')
def analyze(row,program,non_smooth=False):
 validate(row,program)
 starts=json.loads(row['starting_values']);targets=set(json.loads(row['targets']));regs=starts+[None]*(int(row['registers'])-len(starts));done=set(starts)&targets
 initial_by_threshold={str(k):{'targets':set(),'groups':[]} for k in THRESHOLDS}
 runtime_by_threshold={str(k):{'targets':set(),'best':None,'best_exact':None} for k in THRESHOLDS}
 direct=[]
 def snapshot(step):
  pending=targets-done
  for v in sorted(set(regs)-{None}):
   groups=defaultdict(list)
   for t in pending:
    g=math.gcd(v,t)
    if g<10 or g==t:continue
    residual=g
    for prime in (2,3,5):
     while residual%prime==0:residual//=prime
    if non_smooth and residual==1:continue
    groups[g].append(t)
    for cutoff in THRESHOLDS:
     if g>=cutoff:
      runtime_by_threshold[str(cutoff)]['targets'].add(t)
      if step==0:initial_by_threshold[str(cutoff)]['targets'].add(t)
   for g,ts in groups.items():
    if len(ts)<2:continue
    example={'step':step,'known_value':v,'known_is_initial':v in starts,'known_is_target':v in targets,'gcd':g,'factor_is_known_value':g==v,'targets':sorted(ts),'quotients':[t//g for t in sorted(ts)]}
    for cutoff in THRESHOLDS:
     if g<cutoff:continue
     item=runtime_by_threshold[str(cutoff)];best=item['best'];key=(len(ts),int(g==v),g)
     if best is None or key>(len(best['targets']),int(best['factor_is_known_value']),best['gcd']):item['best']=example
     if g==v:
      best=item['best_exact']
      if best is None or (len(ts),g)>(len(best['targets']),best['gcd']):item['best_exact']=example
     if step==0:initial_by_threshold[str(cutoff)]['groups'].append(example)
 snapshot(0)
 for i,(op,a,b,d) in enumerate(program,1):
  x,y=regs[a],regs[b];v=calc(op,x,y)
  if v in targets and v not in done and op=='*':
   for x1 in {x,y}:
    if 100<=x1<v:direct.append({'step':i,'known':x1,'target':v,'other':v//x1})
  regs[d]=v;done.add(v) if v in targets else None;snapshot(i)
 for k in map(str,THRESHOLDS):
  for bucket in (initial_by_threshold[k],runtime_by_threshold[k]):bucket['target_count']=len(bucket.pop('targets'))
  groups=initial_by_threshold[k].pop('groups');initial_by_threshold[k]['best_group']=max(groups,key=lambda x:(len(x['targets']),x['gcd']),default=None)
 return {'id':row['id'],'starts':starts,'target_count':len(targets),'baseline_steps':len(program),'initial':initial_by_threshold,'runtime':runtime_by_threshold,'direct_target_products':direct}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--non-smooth',action='store_true');ap.add_argument('--seed',type=int,default=20261124);ap.add_argument('--sample',type=int,default=20);ap.add_argument('--baseline',type=Path,default=ROOT/'external/asterios_v196/merged_132477.csv');ap.add_argument('--output',type=Path,default=ROOT/'experiments/gcd_known_sample_20.json');args=ap.parse_args()
 data=ROOT/'data/puzzles.csv'
 with data.open(newline='') as f:puzzles={r['id']:r for r in csv.DictReader(f)}
 ids=sorted(random.Random(args.seed).sample(sorted(puzzles),args.sample))
 with args.baseline.open(newline='') as f:programs={r['id']:json.loads(r['program']) for r in csv.DictReader(f) if r['id'] in ids}
 cases=[analyze(puzzles[i],programs[i],args.non_smooth) for i in ids]
 totals={}
 for n in THRESHOLDS:
  k=str(n);totals[k]={'initial_any':sum(c['initial'][k]['target_count']>0 for c in cases),'initial_shared':sum(c['initial'][k]['best_group'] is not None for c in cases),'runtime_any':sum(c['runtime'][k]['target_count']>0 for c in cases),'runtime_shared':sum(c['runtime'][k]['best'] is not None for c in cases),'runtime_shared_exact_value':sum(c['runtime'][k]['best_exact'] is not None for c in cases),'targets_initial':sum(c['initial'][k]['target_count'] for c in cases),'targets_runtime':sum(c['runtime'][k]['target_count'] for c in cases)}
 report={'seed':args.seed,'sampling':'uniform random sample without replacement from sorted scored IDs','sample_size':args.sample,'non_smooth':args.non_smooth,'threshold_definition':'gcd >= cutoff, gcd < target, unknown targets only; known value is currently in a register','puzzles_sha256':sha(data),'baseline_sha256':sha(args.baseline),'totals':totals,'cases':cases}
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('sample IDs',*ids);print(json.dumps(totals,indent=2))
 for c in cases:
  b=c['runtime']['100']['best'];e=c['runtime']['100']['best_exact'];print(c['id'],'initial targets',c['initial']['100']['target_count'],'runtime targets',c['runtime']['100']['target_count'],'best',b,'best-exact',e)
if __name__=='__main__':main()
