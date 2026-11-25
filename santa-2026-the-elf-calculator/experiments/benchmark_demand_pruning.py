"""Compare demand-driven correction with the fixed live-graph solver."""
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor
from depth_graph_study import ROOT, DEFAULT_PUZZLES
from hybrid_graph_search import Construction, live_rollout
from first_solver import validate


def measure(item):
    puzzle, baseline = item
    model = Construction(puzzle)
    out = {}
    for mode in (None,'single','joint'):
        start = time.monotonic()
        program, stats = live_rollout(model,virtual=True,correction_mode=mode)
        validate(puzzle,program)
        out[mode or 'original'] = dict(steps=len(program),seconds=round(time.monotonic()-start,3),
                                       stats=stats,program=program)
    assert out['original']['steps']==baseline
    print(puzzle['id'],*[row['steps'] for row in out.values()],flush=True)
    return puzzle['id'],out


if __name__=='__main__':
    historical = json.loads((ROOT/'reports/hybrid_graph_results.json').read_text())['cases']
    with DEFAULT_PUZZLES.open() as inp:
        puzzles = {r['id']:r for r in csv.DictReader(inp)}
    with ProcessPoolExecutor(max_workers=4) as pool:
        result = dict(pool.map(measure,[(puzzles[r['id']],r['steps']['virtual_fixed']) for r in historical]))
    (ROOT/'reports/demand_pruning.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
