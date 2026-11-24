#!/usr/bin/env python3
"""Reproducible matched single/multi-parent graph search on a stratified sample."""
import argparse, csv, hashlib, json, random, subprocess, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from first_solver import validate
csv.field_size_limit(1_000_000)
def load(path):
    with path.open(newline='') as f: return {r['id']:json.loads(r['program']) for r in csv.DictReader(f)}
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def encode(p, parents, rounds, seed):
    starts=json.loads(p['starting_values']); targets=json.loads(p['targets'])
    lines=[[1],[p['value_limit'],p['registers'],rounds,0,seed],[len(starts),*starts],[len(targets),*sorted(targets)],[len(parents)]]
    for tape in parents: lines.append([len(tape)]); lines.extend(tape)
    return '\n'.join(' '.join(map(str,line)) for line in lines)+'\n'
def run(exe,p,parents,rounds,seed):
    result=subprocess.run([str(exe)],input=encode(p,parents,rounds,seed),text=True,capture_output=True,check=True,timeout=300)
    data=result.stdout.split(); count=int(data[0]);
    if len(data)!=1+count*4: raise ValueError('bad solver output')
    tape=[[data[i],int(data[i+1]),int(data[i+2]),int(data[i+3])] for i in range(1,len(data),4)]
    validate(p,tape)
    if len(tape)>len(parents[0]): raise ValueError('solver regressed')
    return tape
def main():
    a=argparse.ArgumentParser();a.add_argument('--baseline',type=Path,required=True);a.add_argument('--donor',type=Path,required=True);a.add_argument('--bin-dir',type=Path,required=True);a.add_argument('--sample',type=int,default=40);a.add_argument('--rounds',type=int,default=240);a.add_argument('--jobs',type=int,default=4);a.add_argument('--out',type=Path,required=True);args=a.parse_args()
    with (ROOT/'data/puzzles.csv').open(newline='') as f: puzzles={p['id']:p for p in csv.DictReader(f)}
    base=load(args.baseline);donor=load(args.donor)
    ids=sorted(puzzles,key=lambda i:(len(base[i]),i)); rng=random.Random(20261123)
    ids=[ids[(j*len(ids)+rng.randrange(len(ids)))//args.sample] for j in range(args.sample)]
    def task(ident):
        p=puzzles[ident]; par=base[ident]; alt=donor[ident]; seed=290000+int(ident[-4:]); t=time.monotonic()
        one=run(args.bin_dir/'anneal_seeded',p,[par],args.rounds,seed)
        multi=run(args.bin_dir/'anneal_seeded',p,[par,alt],args.rounds,seed)
        return ident,one,multi,round(time.monotonic()-t,3)
    results=[];new=dict(base)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for ident,one,multi,seconds in pool.map(task,ids):
            original=len(base[ident]); best=min([base[ident],one,multi],key=len);new[ident]=best
            results.append({'id':ident,'base':original,'donor':len(donor[ident]),'single':len(one),'multi':len(multi),'best':len(best),'seconds':seconds})
            print(ident,original,len(one),len(multi),flush=True)
    args.out.mkdir(parents=True,exist_ok=True)
    dest=args.out/'candidate.csv'
    with dest.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['id','program']);w.writerows((i,json.dumps(new[i],separators=(',',':'))) for i in sorted(new))
    for i,p in puzzles.items():validate(p,new[i])
    report={'puzzles_sha256':digest(ROOT/'data/puzzles.csv'),'baseline_sha256':digest(args.baseline),'donor_sha256':digest(args.donor),'binary_sha256':digest(args.bin_dir/'anneal_seeded'),'selection':'length stratified with RNG 20261123','rounds_per_arm':args.rounds,'results':results,'score':sum(map(len,new.values())),'candidate_sha256':digest(dest)}
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('score',report['score'],'single savings',sum(r['base']-r['single'] for r in results),'multi savings',sum(r['base']-r['multi'] for r in results),'union savings',sum(r['base']-r['best'] for r in results),flush=True)
if __name__=='__main__':main()
