"""Verify whole programs, then repair the best new rollout and summarize both test sets."""
import csv
import json
from concurrent.futures import ProcessPoolExecutor

from baseline_lineage import DEFAULT_PUZZLES, ROOT
from benchmark_hybrid_graph import SEARCH_SEEDS
from first_solver import validate
from hybrid_graph_search import local_repair, shared_helper_repair

REPORTS = ROOT/'reports'


def load(filename):
    return json.loads((REPORTS/filename).read_text())


def finish(item):
    puzzle,case,shared,bandit,archive,group = item
    steps = dict(case['steps'])
    options = {'repair_own':case['programs']['repair_own']}
    for method,program in case['programs'].items():
        assert validate(puzzle,program)[0] == steps[method]
    for name in ('repair_own','repair_public'):
        record = shared[name]
        steps['shared_'+name] = validate(puzzle,record['program'])[0]
        assert steps['shared_'+name] == record['after']
    options['shared_repair_own'] = shared['repair_own']['program']
    for name in ('round_robin','ucb'):
        options[name] = bandit[name]['program']
        steps[name] = validate(puzzle,options[name])[0]
        assert steps[name]==bandit[name]['steps']
    winner = min(options,key=lambda k:len(options[k]))
    best = options[winner]
    patches = []
    if winner in ('round_robin','ucb'):
        original = best
        for seed in SEARCH_SEEDS:
            candidate, wins = local_repair(puzzle,original,seed,budget=32,reschedule=True)
            candidate, joint = shared_helper_repair(puzzle,candidate,seed,rounds=5)
            if len(candidate)<len(best):
                best = candidate
                patches = wins+joint
    steps['own_final'] = validate(puzzle,best)[0]
    steps['previous_anchor'] = validate(puzzle,archive)[0]
    return dict(id=case['id'],group=group,steps=steps,source=winner,
                final_patches=patches,own_final_program=best)


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as f:
        puzzles = {p['id']:p for p in csv.DictReader(f)}
    with (ROOT/'experiments/anchor_scored_submission.csv').open() as f:
        archives = {r['id']:r['program'] for r in csv.DictReader(f)}
    all_sets = [load('hybrid_graph_benchmark.json'),load('hybrid_graph_holdout.json')]
    shared = {r['id']:r for r in load('hybrid_shared_repair.json')}
    bandit = {r['id']:r for r in load('hybrid_rollout_bandit.json')}
    items = []
    for group,data in zip(('initial_random','holdout_random'),all_sets):
        for case in data['cases']:
            i = case['id']
            items.append((puzzles[i],case,shared[i],bandit[i],json.loads(archives[i]),
                          group if i in data['sample'] else 'diagnostic'))
    assert len({t[1]['id'] for t in items}) == len(items)
    with ProcessPoolExecutor(max_workers=4) as pool:
        cases = list(pool.map(finish,items))
    totals = {}
    for group in ('initial_random','holdout_random','diagnostic','random_combined'):
        rows = [r for r in cases if r['group']==group or
                (group=='random_combined' and r['group']!='diagnostic')]
        totals[group] = {name:sum(r['steps'][name] for r in rows) for name in rows[0]['steps']}
    (REPORTS/'hybrid_graph_results.json').write_text(json.dumps(dict(totals=totals,cases=cases),
                                                               separators=(',',':'))+'\n')
    print(json.dumps(totals,indent=2))
