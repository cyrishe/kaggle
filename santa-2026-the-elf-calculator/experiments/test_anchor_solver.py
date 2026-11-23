import csv,json,time,collections
from first_solver import build,validate
from anchor_solver import solve
with open('data/practice_puzzles.csv',newline='') as f: rows=list(csv.DictReader(f))
groups=collections.defaultdict(list)
for p in rows:groups[p['family']].append(p)
selection=[]
for fam,ps in sorted(groups.items()):
 for i in range(4):selection.append(ps[i*(len(ps)-1)//3])
records=[]; start=time.monotonic()
for p in selection:
 baseline=[];new=[]
 for base in range(2,min(40,int(p['value_limit']),47-len(json.loads(p['starting_values'])))+1):
  try:
   program=build(p,base);validate(p,program);baseline.append((len(program),base))
  except ValueError:pass
 for base in (2,3,4,6,8,12,16,20,24,28,32,36,40):
  try:
   program=solve(p,base);validate(p,program);new.append((len(program),base))
  except ValueError:pass
 old=min(baseline) if baseline else None; best=min(new) if new else None
 records.append({'id':p['id'],'family':p['family'],'baseline_steps':old[0] if old else '', 'baseline_base':old[1] if old else '', 'anchor_steps':best[0] if best else '', 'anchor_base':best[1] if best else '', 'difference':best[0]-old[0] if old and best else ''})
 print(p['id'],p['family'],'baseline',old,'anchor',best,flush=True)
with open('experiments/anchor_practice_comparison.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
print('elapsed',round(time.monotonic()-start,1))
