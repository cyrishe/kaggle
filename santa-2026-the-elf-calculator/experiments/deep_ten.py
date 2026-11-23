import csv,json,time,concurrent.futures
from anchor_solver import solve
from first_solver import validate
from prune_program import prune
csv.field_size_limit(1000000)
ids=['scored_0001','scored_0112','scored_0223','scored_0334','scored_0445','scored_0556','scored_0667','scored_0778','scored_0889','scored_1000']
def worker(x):
 p,orig=x;old=json.loads(orig);best=prune(p,old);base='pruned';counts=[]
 for b in [16,24,32,36,40]:
  try:
   v=prune(p,solve(p,b,extended=True,lookahead=True));counts.append((b,len(v)))
   if len(v)<len(best):best=v;base=b
  except ValueError:pass
 validate(p,best)
 return dict(id=p['id'],old=len(old),new=len(best),saved=len(old)-len(best),base=base,candidates=json.dumps(counts),program=json.dumps(best,separators=(',',':')))
if __name__=='__main__':
 with open('data/puzzles.csv',newline='') as f: ps={r['id']:r for r in csv.DictReader(f) if r['id'] in ids}
 with open('experiments/anchor_scored_submission.csv',newline='') as f: prev={r['id']:r['program'] for r in csv.DictReader(f) if r['id'] in ids}
 results=[];start=time.monotonic()
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
  fs=[pool.submit(worker,(ps[i],prev[i])) for i in ids]
  for f in concurrent.futures.as_completed(fs):
   x=f.result();results.append(x);print(x['id'],x['old'],x['new'],'saved',x['saved'],flush=True)
 results.sort(key=lambda x:x['id'])
 with open('experiments/deep_ten_comparison.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['id','old','new','saved','base','candidates'],extrasaction='ignore');w.writeheader();w.writerows(results)
 with open('experiments/deep_ten_programs.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['id','program'],extrasaction='ignore');w.writeheader();w.writerows(results)
 print('TOTAL',sum(x['old'] for x in results),sum(x['new'] for x in results),'seconds',round(time.monotonic()-start,1))
