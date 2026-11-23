#!/usr/bin/env python3
"""Evaluate legal positional and near-square candidates against the sample."""
import csv,json,time,argparse
from pathlib import Path
from first_solver import build,validate
csv.field_size_limit(1_000_000)
with open('data/puzzles.csv',newline='') as f: puzzles=list(csv.DictReader(f))
ap=argparse.ArgumentParser(); ap.add_argument('--sample',type=int,default=20); args=ap.parse_args()
if not 1<=args.sample<=len(puzzles): raise ValueError('invalid sample size')
if args.sample==1: puzzles=puzzles[:1]
elif args.sample<len(puzzles): puzzles=[puzzles[i*(len(puzzles)-1)//(args.sample-1)] for i in range(args.sample)]
with open('data/sample_submission.csv',newline='') as f: sample={r['id']:json.loads(r['program']) for r in csv.DictReader(f)}
start=time.monotonic(); records=[]; programs=[]
for ix,p in enumerate(puzzles,1):
 best=None
 for base in range(2,min(40,int(p['value_limit']),47-len(json.loads(p['starting_values'])))+1):
  try:
   program=build(p,base); validate(p,program)
  except ValueError: continue
  if best is None or len(program)<len(best[1]): best=(base,program)
 ref=sample[p['id']]; validate(p,ref)
 if best is None: chosen=ref; base=''; source='sample'
 elif len(best[1])<len(ref): base,chosen=best;source='solver'
 else: base=best[0];chosen=ref;source='sample'
 records.append({'id':p['id'],'base':base,'candidate_steps':len(best[1]) if best else '', 'sample_steps':len(ref),'chosen_steps':len(chosen),'source':source})
 programs.append({'id':p['id'],'program':json.dumps(chosen,separators=(',',':'))})
 if ix%5==0: print(f'{ix}/{len(puzzles)} elapsed={time.monotonic()-start:.1f}s',flush=True)
prefix='full' if len(puzzles)==1000 else 'sample'
with open(f'experiments/{prefix}_comparison.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
with open(f'experiments/{prefix}_programs.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['id','program']);w.writeheader();w.writerows(programs)
print('solved',sum(r['candidate_steps']!='' for r in records),'improved',sum(r['source']=='solver' for r in records),'sample total',sum(r['sample_steps'] for r in records),'selected total',sum(r['chosen_steps'] for r in records),flush=True)
