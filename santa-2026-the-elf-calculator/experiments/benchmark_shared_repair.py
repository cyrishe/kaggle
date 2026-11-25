"""Apply the same shared-helper search to our own and public incumbents."""
import argparse
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from baseline_lineage import DEFAULT_PUZZLES, ROOT
from benchmark_hybrid_graph import SEARCH_SEEDS
from first_solver import validate
from hybrid_graph_search import shared_helper_repair


def run(item):
    puzzle, case = item
    result = dict(id=case['id'])
    for source in ('repair_own', 'repair_public'):
        start = time.monotonic()
        initial = case['programs'][source]
        best = initial
        runs = []
        for seed in SEARCH_SEEDS:
            candidate, wins = shared_helper_repair(puzzle, initial, seed, rounds=5)
            validate(puzzle,candidate)
            runs.append(dict(seed=seed,steps=len(candidate),wins=wins))
            if len(candidate)<len(best):
                best = candidate
        result[source] = dict(before=len(initial),after=len(best),runs=runs,program=best,
                              seconds=round(time.monotonic()-start,3))
    print(result['id'], [(result[k]['before'],result[k]['after']) for k in ('repair_own','repair_public')], flush=True)
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/hybrid_shared_repair.json')
    args = parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:
        puzzles = {p['id']:p for p in csv.DictReader(f)}
    items = [(puzzles[c['id']], c) for path in args.reports for c in json.loads(path.read_text())['cases']]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, items))
    args.output.write_text(json.dumps(rows,separators=(',',':'))+'\n')
