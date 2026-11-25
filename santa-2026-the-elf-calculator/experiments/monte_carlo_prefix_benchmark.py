"""Five hundred independent live rollouts, then 200 fresh versus 200 checkpoint repairs."""
import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor

from benchmark_hybrid_graph import load_reference
from capped_path_walk import CASES, SEED, explore, update_elites
from first_solver import validate
from hybrid_graph_search import Construction
from baseline_lineage import DEFAULT_PUZZLES, ROOT


def completed(archive, item):
    if item[0]['status']=='full':
        update_elites(archive,item)


def result(archive,rows):
    return dict(best=archive[0][0]['steps'] if archive else None,
                program=archive[0][2] if archive else None,
                winner=archive[0][0]['trial'] if archive else None,
                completed=sum(r['status']=='full' for r in rows),
                distinct=len({r['key'] for r in rows if r['status']=='full'}),
                maximum_targets=max(r['covered'] for r in rows),
                seconds=round(sum(r['seconds'] for r in rows),3))


def run(p):
    m = Construction(p)
    elite,rows = [],[]
    curve = {}
    cap = 150
    for i in range(500):
        trial = explore(m,i,cap)
        completed(elite,trial)
        rows.append(trial[0])
        if i+1 in (50,100,200,250,400,500):
            curve[i+1]=result(elite,rows)['best']
    initial=result(elite,rows)
    fresh,repair = elite.copy(),elite.copy()
    a,b = [],[]
    journal = []
    for i in range(500,700):
        new = explore(m,i,cap)
        a.append(new[0])
        completed(fresh,new)
        # Parent selection only uses complete legal programs; if none exists,
        # the matched fallback is the same new independent rollout.
        rng = random.Random(SEED*1000+i)
        if repair:
            parent = rng.choice(repair)
            info,history,_ = parent
            cuts = [j for j,c in enumerate(history) if 0.25*info['steps']<=len(c.program)<=0.75*info['steps']
                    and 0<len(c.hits)<len(m.targets)]
        else:
            cuts=[]
        if cuts:
            j=rng.choice(cuts)
            revised=explore(m,i,cap,history[:j+1],info['trial'])
        else:
            revised=new
        before = repair[0][0]['steps'] if repair else None
        completed(repair,revised)
        if before is not None and repair[0][0]['steps']<before:
            journal.append(dict(trial=i,parent=revised[0]['parent'],prefix_steps=revised[0]['prefix_steps'],
                                prefix_hits=revised[0]['prefix_hits'],before=before,after=repair[0][0]['steps']))
        b.append(revised[0])
    out=dict(targets=len(m.targets),public=len(load_reference(p['id'])),cap=cap,curve=curve,initial=initial,
             fresh=result(fresh,a),repair=result(repair,b),repairs=sum(r['parent'] is not None for r in b),
             improvements=journal,runs=dict(initial=rows,fresh=a,repair=b))
    for arm in ('initial','fresh','repair'):
        if out[arm]['program'] is not None:
            assert validate(p,out[arm]['program'])[0]==out[arm]['best']<=cap
    print(p['id'],[(k,out[k]['best'],out[k]['completed']) for k in ('initial','fresh','repair')],flush=True)
    return p['id'],out


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as file:
        puzzles = {r['id']:r for r in csv.DictReader(file)}
    with ProcessPoolExecutor(max_workers=4) as pool:
        out=dict(pool.map(run,[puzzles[i] for i in CASES]))
    (ROOT/'reports/monte_carlo_prefix_benchmark.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
