"""Regrow a public solution's suffix using only values alive at the cut."""
import csv
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from baseline_lineage import ROOT, DEFAULT_PUZZLES
from benchmark_hybrid_graph import load_reference
from capped_path_walk import Checkpoint, explore
from export_50_baseline_cases import replay
from first_solver import validate
from hybrid_graph_search import Construction, local_repair


def run(p):
    program=load_reference(p['id'])
    starts=json.loads(p['starting_values'])
    goals=set(json.loads(p['targets']))
    regs=starts+[None]*(int(p['registers'])-len(starts))
    hits=set(starts)&goals
    fractions=(0.50,0.65,0.80,0.90)
    cuts={round(len(program)*f):f for f in fractions}
    rows=[]
    best=program
    for n,_,_,_,_,_,dest,v,_ in replay(p,program):
        regs[dest]=v
        if v in goals:
            hits.add(v)
        if n not in cuts:
            continue
        slots={value:i for i,value in enumerate(regs) if value is not None}
        # Pin up to six small live seeds to keep F2 bounded; all other live values
        # remain immediately available. No suffix instruction informs the ranking.
        seeds=sorted(slots)[:6]
        model=Construction(dict(p,starting_values=json.dumps(seeds)))
        model.puzzle=p  # final replay must start at the true official register layout
        cp=Checkpoint(tuple(map(tuple,program[:n])),tuple(slots.items()),frozenset(hits))
        lengths=Counter()
        failures=Counter()
        candidate=None
        for trial in range(50):
            info,_,out=explore(model,trial,150,[cp])
            if out is not None:
                validate(p,out)
                lengths[len(out)] += 1
                if candidate is None or len(out)<len(candidate):
                    candidate=out
                if len(out)<len(best):
                    best=out
            else:
                failures[info['status']] += 1
        rows.append(dict(fraction=cuts[n],cut=n,hits=len(hits),lengths=lengths,
                         failures=failures,best_program=candidate))
    improved,_=local_repair(p,best,11,budget=32,reschedule=True)
    validate(p,improved)
    out=dict(id=p['id'],public_steps=len(program),target_count=len(goals),cuts=rows,
             best_including_parent=len(best),after_repair=len(improved),program=improved)
    print(p['id'],[(r['cut'],r['failures'],min(r['lengths'],default=None)) for r in rows],flush=True)
    return out


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as f:
        puzzles={r['id']:r for r in csv.DictReader(f)}
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(run,[puzzles[i] for i in ('scored_0253','scored_0667')]))
    (ROOT/'reports/public_prefix_walk.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
