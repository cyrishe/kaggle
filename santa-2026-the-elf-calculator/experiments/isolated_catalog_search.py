"""Jointly extract a small arithmetic DAG from the solo-path values and recurring gaps."""
import argparse
import csv
import json
import math
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from bench_isolated_merge import ROOT, save
from converge_target_paths import improve
from first_solver import validate
from hybrid_graph_search import program_rules
from probe_baseline_pair import compile_values


def gap_candidates(values, catalog, starts, limit, budget=256):
    owners = {v:0 for v in values}
    for idx, alternatives in enumerate(catalog.values()):
        for path in alternatives:
            for _,_,_,v in path:
                owners[v] |= 1 << idx
    popular = sorted(owners, key=lambda v:(-owners[v].bit_count(), v))[:28]
    seen = {}
    frequency = Counter()
    def suggest(h, mask):
        if h not in values and 0 < h <= limit and mask:
            seen[h] = seen.get(h,0) | mask
            frequency[h] += 1
    ordered = sorted(values)
    for i,v in enumerate(ordered):
        for a in set(ordered[max(0,i-9):i] + popular + starts):
            if v <= a:
                continue
            mask = owners[v] | owners.get(a,0)
            suggest(v-a,mask)
            q,r = divmod(v,a)
            if r == 0:
                suggest(q,mask)
            elif r in values or a-r in values:
                suggest(q if r in values else q+1,mask)
            if owners[v] & ~owners.get(a,0) and owners.get(a,0) & ~owners[v]:
                h = math.gcd(v,a)
                if h>1:
                    suggest(h,mask)
    return sorted(seen,key=lambda h:(-seen[h].bit_count(),-frequency[h],h))[:budget]


def extract(p, binary, budget, seed, value_set, source_paths):
    values = sorted(value_set)
    starts = json.loads(p['starting_values'])
    goals = json.loads(p['targets'])
    index = {v:i for i,v in enumerate(values)}
    lines = [f"{len(values)} {len(starts)} {len(goals)} {p['registers']} 4096",
             ' '.join(str(index[v]) for v in starts), ' '.join(str(index[v]) for v in goals)]
    lines.insert(1,' '.join(map(str, values)))
    lines.append(str(len(source_paths)))
    for path in source_paths:
        lines.append(str(len(path)))
        for op,a,b,v in path:
            lines.append(f'{op} {index[a]} {index[b]} {index[v]}')
    output = subprocess.check_output([binary,str(budget),str(seed)],input='\n'.join(lines)+'\n',text=True)
    stream = iter(output.splitlines())
    nodes,rules = map(int,next(stream).split())
    arms = {}
    best = None
    for header in stream:
        method,trials,n,peak,seconds,unique,*curve = header.split()
        path = []
        for _ in range(int(n)):
            op,a,b,v = next(stream).split()
            path.append((op,values[int(a)],values[int(b)],values[int(v)]))
        prog = compile_values(p,path,goals)
        assert validate(p,prog)[0]==int(n)
        arms[method]=dict(steps=int(n),peak=int(peak),curve=list(map(int,curve)))
        if best is None or len(prog)<len(best):
            best=prog
    return best,dict(nodes=nodes,rules=rules,arms=arms)


def run(job):
    p,work,binary,budget,seed = job
    i = p['id']
    seed += int(i[-4:])
    row = json.loads((work/'cases'/f'{i}.json').read_text())
    catalog = json.loads((work/'catalog'/f'{i}.json').read_text())
    starts = json.loads(p['starting_values'])
    goals = json.loads(p['targets'])
    candidates = [row['programs'][k] for k in ('best','rewire_from_choices','rewire_from_equal','choices','equal')]
    sources = []
    for prog in candidates:
        path = program_rules(p,prog)
        if len(set(r[-1] for r in path)) == len(path) and path not in sources:
            sources.append(path)
    values = set(starts) | set(goals)
    for alts in catalog.values():
        for path in alts:
            values.update(r[-1] for r in path)
    for path in sources:
        values.update(r[-1] for r in path)
    gaps = gap_candidates(values,catalog,starts,int(p['value_limit']))
    best = min(candidates,key=len)
    report = {}
    for label,vs in [('catalog',values),('catalog_and_gaps',values.union(gaps))]:
        prog,details = extract(p,binary,budget,seed,vs,sources)
        details['steps'] = len(prog)
        report[label]=details
        if len(prog)<len(best):
            best=prog
    final, stats = improve(p,best,seed=seed,rounds=5)
    assert validate(p,final)[0] <= len(best)
    report.update(parent=row['steps']['best'],added_gaps=len(gaps),before_last_rewrite=len(best),
                  steps=len(final),program=final,witnesses=stats['witnesses'])
    return i,report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work-dir',type=Path,required=True)
    ap.add_argument('--ids',nargs='+')
    ap.add_argument('--trials',type=int,default=160)
    ap.add_argument('--seed',type=int,default=20261126)
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--output',type=Path,default=ROOT/'reports/isolated_catalog_search.json')
    args=ap.parse_args()
    with (ROOT/'data/puzzles.csv').open() as f:
        ps={p['id']:p for p in csv.DictReader(f)}
    ids=args.ids or sorted(f.stem for f in (args.work_dir/'cases').glob('scored_*.json'))
    rows={}
    with tempfile.TemporaryDirectory() as tmp:
        binary=Path(tmp)/'joint'
        subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('joint_bridge_search.cpp')),'-o',binary],check=True)
        with ProcessPoolExecutor(args.workers) as pool:
            jobs=[pool.submit(run,(ps[i],args.work_dir,binary,args.trials,args.seed)) for i in ids]
            for f in as_completed(jobs):
                i,r=f.result();rows[i]=r
                print(i,r['parent'],r['catalog']['steps'],r['catalog_and_gaps']['steps'],r['steps'],flush=True)
    save(args.output,dict(trials=args.trials,seed=args.seed,cases={i:rows[i] for i in ids}))


if __name__=='__main__':
    main()
