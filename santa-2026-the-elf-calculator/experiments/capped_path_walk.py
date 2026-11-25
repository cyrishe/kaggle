"""Matched independent vs elite-prefix rollouts in a positive-integer register machine."""
import argparse
import csv
import hashlib
import json
import random
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from baseline_lineage import DEFAULT_PUZZLES, ROOT
from first_solver import validate
from hybrid_graph_search import Construction, live_rollout, local_repair, program_rules, shared_helper_repair

SEED = 20261125
CASES = ('scored_0253', 'scored_0667', 'scored_0810', 'scored_0035')


@dataclass
class Checkpoint:
    program: tuple
    slots: tuple
    hits: frozenset


class Trace:
    def __init__(self, cap, history=()):
        self.cap = cap
        self.history = list(history)
        self.prefix = self.history[-1] if self.history else None

    def record(self, program, slots, hits):
        self.history.append(Checkpoint(tuple(tuple(op) for op in program), tuple(slots.items()), frozenset(hits)))


def fingerprint(puzzle, program):
    rules = program_rules(puzzle, program)
    key = sorted((op, min(a,b), max(a,b), v) if op in ('+','*') else (op,a,b,v)
                 for op,a,b,v in rules)
    return hashlib.sha256(repr(key).encode()).hexdigest()


def explore(model, trial, cap, history=(), parent=None):
    trace = Trace(cap,history)
    start = time.perf_counter()
    policy = ('order','shared','residual')[trial%3]
    program, stats = live_rollout(model,SEED+trial,virtual=True,policy=policy,walk=trace)
    success = program is not None
    if success:
        assert validate(model.puzzle,program)[0]<=cap
    covered = len(model.targets) if success else stats.get('covered',len(trace.history[-1].hits) if trace.history else 0)
    spent = len(program) if success else stats.get('spent',len(trace.history[-1].program) if trace.history else 0)
    code = trace.prefix.program if trace.prefix else ()
    info = dict(trial=trial,seed=SEED+trial,policy=policy,parent=parent,prefix_steps=len(code),
                prefix_hits=len(trace.prefix.hits) if code else 0,
                status='full' if success else ('cutoff' if stats.get('cutoff') else 'registers'),
                steps=spent,covered=covered,seconds=time.perf_counter()-start)
    if success:
        sig = fingerprint(model.puzzle,program)
    else:
        sig = hashlib.sha256(repr(trace.history[-1].program if trace.history else ()).encode()).hexdigest()
    info['key'] = sig
    return info, trace.history, program


def update_elites(elites, result):
    info = result[0]
    if not result[1] or any(e[0]['key']==info['key'] for e in elites):
        return
    elites.append(result)
    elites.sort(key=lambda e:(e[0]['status']!='full',-e[0]['covered'],e[0]['steps'],e[0]['trial']))
    del elites[5:]


def run_case(args):
    puzzle,cap,attempts = args
    model = Construction(puzzle)
    def summary(runs):
        counts = Counter(r['status'] for r in runs)
        full = [r for r in runs if r['status']=='full']
        return dict(status=counts,best=min((r['steps'] for r in full),default=None),
                    distinct_full=len({r['key'] for r in full}),max_hits=max(r['covered'] for r in runs),
                    seconds=round(sum(r['seconds'] for r in runs),2),runs=runs)
    independent, guided = [], []
    archives = [[],[]]
    rng = random.Random(SEED+int(puzzle['id'][-4:]))
    for i in range(attempts):
        fresh = explore(model,i,cap)
        independent.append(fresh[0])
        update_elites(archives[0],fresh)
        if i<attempts//4 or i%10==0 or not archives[1]:
            result = fresh
        else:
            parent = rng.choices(archives[1],weights=[1/(j+1) for j in range(len(archives[1]))])[0]
            old,history,_ = parent
            eligible = [j for j,p in enumerate(history) if 0.5*old['steps']<=len(p.program)<=0.85*old['steps']
                        and len(p.hits)<len(model.targets)]
            if not eligible:
                result = fresh
            else:
                cut = rng.choice(eligible)
                result = explore(model,i,cap,history[:cut+1],old['trial'])
                result[0]['parent_length'] = old['steps'] if old['status']=='full' else None
                result[0]['identical_graph'] = old['key']==result[0]['key']
        guided.append(result[0])
        update_elites(archives[1],result)
    out = dict(id=puzzle['id'],targets=len(model.targets),cap=cap,independent=summary(independent),guided=summary(guided))
    # Equal post-search budget for the three best distinct graphs in each arm.
    for name,elite in zip(('independent','guided'),archives):
        leaders=[]
        for info,history,program in elite[:3]:
            if program is None:
                continue
            best = program
            for seed in (11,29):
                change,_ = local_repair(puzzle,program,seed,budget=32,reschedule=True)
                change,_ = shared_helper_repair(puzzle,change,seed,rounds=5)
                if len(change)<len(best):
                    best=change
            validate(puzzle,best)
            leaders.append(dict(trial=info['trial'],steps=len(program),repaired=len(best),program=best,
                                original=program,checkpoints=[(len(c.program),sorted(c.hits)) for c in history]))
        out[name]['leaders']=leaders
    print(out['id'],[(a,out[a]['status'],out[a]['best']) for a in ('independent','guided')],flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cap',type=int,default=150)
    parser.add_argument('--trials',type=int,default=200)
    parser.add_argument('--ids',nargs='+',default=CASES)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--output',type=str,default='capped_path_walk.json')
    args=parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:
        puzzles={r['id']:r for r in csv.DictReader(f)}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows=list(pool.map(run_case,[(puzzles[i],args.cap,args.trials) for i in args.ids]))
    (ROOT/'reports'/args.output).write_text(json.dumps(rows,separators=(',',':'))+'\n')
