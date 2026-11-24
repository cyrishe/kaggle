#!/usr/bin/env python3
"""Replay sample programs and list nearest mathematical squares per target."""
import csv,json,math,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from first_solver import validate
csv.field_size_limit(1000000)
def main():
 ids=['scored_0901','scored_0810','scored_0654','scored_0556'];data=ROOT/'data/puzzles.csv';baseline=ROOT/'external/asterios_v196/merged_132477.csv'
 with data.open(newline='') as f:puzzles={r['id']:r for r in csv.DictReader(f) if r['id'] in ids}
 with baseline.open(newline='') as f:programs={r['id']:json.loads(r['program']) for r in csv.DictReader(f) if r['id'] in ids}
 cases=[]
 for ident in ids:
  row=puzzles[ident];program=programs[ident];validate(row,program);start=json.loads(row['starting_values']);targets=set(json.loads(row['targets']));regs=start+[None]*(int(row['registers'])-len(start));steps=[];seen=set(start)&targets
  for i,(op,a,b,d) in enumerate(program,1):
   x,y=regs[a],regs[b]
   if op=='+':v=x+y
   elif op=='-':v=x-y
   elif op=='*':v=x*y
   elif op=='/':v=x//y
   else:raise ValueError(op)
   first=v in targets and v not in seen;seen.add(v) if v in targets else None
   steps.append({'step':i,'operation':op,'left':x,'right':y,'value':v,'first_target':first});regs[d]=v
  squares=[]
  for t in sorted(targets):
   n=math.isqrt(t);choices=[n,n+1];k=min(choices,key=lambda k:(abs(k*k-t),k));squares.append({'target':t,'nearest_root':k,'nearest_square':k*k,'target_minus_square':t-k*k,'square_legal':k*k<=int(row['value_limit'])})
  cases.append({'id':ident,'starting_values':start,'targets':sorted(targets),'value_limit':int(row['value_limit']),'steps':steps,'nearest_squares':squares})
 out={'puzzles_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),'cases':cases};(ROOT/'experiments/product_anchor_study.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print('replayed',len(cases),'cases',[(x['id'],len(x['steps'])) for x in cases])
if __name__=='__main__':main()
