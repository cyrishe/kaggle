"""Solve quotient targets together and lift them back into a full legal program."""
import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor

from baseline_lineage import DB, DEFAULT_PUZZLES
from first_solver import validate
from hybrid_graph_search import Construction, compile_changes, live_rollout, program_rules, rooted_rules


def schedule(p, rules, extra, orders):
    starts = json.loads(p['starting_values'])
    goals = json.loads(p['targets'])
    available = set(starts)
    stream = []
    pending = extra.copy()
    def lift():
        for t,rule in list(pending.items()):
            if t in available:
                del pending[t]
            elif rule[1] in available and rule[2] in available:
                stream.append(rule)
                available.add(t)
                del pending[t]
    lift()
    for rule in rules:
        stream.append(rule)
        available.add(rule[-1])
        lift()
    if pending:
        raise ValueError('quotient or factor missing')
    options = [compile_changes(p,stream,goals)]
    original = {}
    for rule in rules:
        original.setdefault(rule[-1],rule)
    for graph in (extra|original, original|extra):
        for order in orders:
            try:
                sequence = rooted_rules(starts,order,graph)
            except ValueError:
                continue
            trial = compile_changes(p,sequence,goals)
            options.append(trial)
    return min((prog for prog in options if prog is not None),key=len,default=None)


def run_job(job):
    puzzle,groups = job
    model = Construction(puzzle)
    goals = model.targets[:]
    # Keep the broadest factor and alternatives with different target memberships.
    selected = []
    covered_sets = set()
    for f,_,members in groups:
        signature = tuple(members)
        if signature not in covered_sets:
            covered_sets.add(signature)
            selected.append((f,members))
        if len(selected)==3:
            break
    # Also try a cheap smaller divisor covering the same goals.
    alt = min(groups,key=lambda g:(-len(g[2]),g[0] not in model.shallow,g[0]))
    if alt[0] not in {f for f,_ in selected}:
        selected.append((alt[0],alt[2]))
    records = {}
    controls = {}
    best = None
    winner = None
    for f,members in selected:
        complement = [t for t in goals if t not in members]
        target_orders = [goals,members+complement]
        for order in target_orders:
            key = tuple(order)
            if key in controls:
                continue
            model.targets = order
            plain,_ = live_rollout(model,virtual=True)
            if plain is None:
                controls[key] = None
            else:
                priced = schedule(puzzle,program_rules(puzzle,plain),{},target_orders)
                controls[key] = min(len(plain),len(priced) if priced is not None else len(plain))

        quotients = [t//f for t in members]
        proxy_goals = list(dict.fromkeys([f]+quotients+complement))
        proxy = dict(puzzle,targets=json.dumps(proxy_goals))
        submodel = Construction(proxy)
        extra = {t:('*',f,t//f,t) for t in members}
        sizes = []
        for order in dict.fromkeys([tuple(sorted(proxy_goals)),tuple(proxy_goals)]):
            submodel.targets = list(order)
            program,_ = live_rollout(submodel,virtual=True)
            if program is None:
                sizes.append(None)
                continue
            trial = schedule(puzzle,program_rules(proxy,program),extra,target_orders)
            sizes.append(len(trial) if trial is not None else None)
            if trial is not None and (best is None or len(trial)<len(best)):
                validate(puzzle,trial)
                best,winner = trial,f
        records[f]=sizes

    order_control = min(v for v in controls.values() if v is not None)
    # Match the number of construction attempts. The extra direct searches vary
    # target order inside blocks of four without changing their arithmetic.
    budget = sum(map(len,records.values()))
    rng = random.Random(puzzle['id']+'-direct-order-control')
    for _ in range(20*budget):
        if len(controls)>=budget:
            break
        order=goals.copy()
        for start in range(0,len(order),4):
            block=order[start:start+4]
            rng.shuffle(block)
            order[start:start+4]=block
        if tuple(order) in controls:
            continue
        model.targets=order
        plain,_=live_rollout(model,virtual=True)
        if plain is None:
            controls[tuple(order)]=None
        else:
            priced=schedule(puzzle,program_rules(puzzle,plain),{},[order,goals])
            controls[tuple(order)]=min(len(plain),len(priced) if priced is not None else len(plain))
    return puzzle['id'], dict(control=min(v for v in controls.values() if v is not None),
                              order_control=order_control,quotient_attempts=budget,
                              controls=list(controls.values()),trials=records,
                              factor=winner,steps=len(best) if best is not None else None,program=best)


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as file:
        puzzles = {p['id']:p for p in csv.DictReader(file)}
    features = json.loads(DB.with_name('factor_routing.json').read_text())['cases']
    sample = json.loads(DB.with_name('factor_routing_benchmark.json').read_text())
    jobs = [(puzzles[i],features[i]['exact'] or features[i]['relaxed'])
            for i,r in sample.items() if r['route'] in ('factor','weak_factor')]
    with ProcessPoolExecutor(max_workers=4) as pool:
        out=dict(pool.map(run_job,jobs))
    DB.with_name('factor_quotient_programs.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    print('tested quotient construction on',len(out),'puzzles')
