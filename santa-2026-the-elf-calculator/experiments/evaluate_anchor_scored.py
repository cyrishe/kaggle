#!/usr/bin/env python3
"""Compare anchor solver against the complete first-version submission."""
import csv,json,time,concurrent.futures,os
from anchor_solver import solve
from first_solver import validate
csv.field_size_limit(1_000_000)
def one(item):
 p,old=item; oldops=json.loads(old);validate(p,oldops);best=oldops;base=''; count=0
 bases=(2,4,8,12,16,24,32,36,40) if int(p['value_limit'])<100 else (8,16,24,32,36,40)
 for b in bases:
  try:
   candidate=solve(p,b);count+=1
   if len(candidate)<len(best):best=candidate;base=b
  except ValueError:continue
 validate(p,best)
 return {'id':p['id'],'baseline_steps':len(oldops),'new_steps':len(best),'improvement':len(oldops)-len(best),'base':base,'candidates':count,'program':json.dumps(best,separators=(',',':'))}

def main():
 with open('data/puzzles.csv',newline='') as f:p=list(csv.DictReader(f))
 with open('experiments/full_programs.csv',newline='') as f:previous={r['id']:r['program'] for r in csv.DictReader(f)}
 assert len(p)==1000 and len(previous)==1000 and set(previous)=={r['id'] for r in p}
 start=time.monotonic();results=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=6) as ex:
  futures=[ex.submit(one,(r,previous[r['id']])) for r in p]
  for f in concurrent.futures.as_completed(futures):
   results.append(f.result())
   if len(results)%50==0:print(f'{len(results)}/1000 elapsed={time.monotonic()-start:.1f}s',flush=True)
 results.sort(key=lambda x:x['id'])
 with open('experiments/anchor_scored_comparison.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['id','baseline_steps','new_steps','improvement','base','candidates'],extrasaction='ignore');w.writeheader();w.writerows(results)
 with open('experiments/anchor_scored_submission.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['id','program'],extrasaction='ignore');w.writeheader();w.writerows(results)
 print('TOTAL',sum(r['baseline_steps'] for r in results),sum(r['new_steps'] for r in results),'IMPROVED',sum(r['improvement']>0 for r in results),'NO_CANDIDATE',sum(r['candidates']==0 for r in results),flush=True)
if __name__=='__main__': main()
