"""Test target-derived subgraphs against the same normalized executable incumbent."""
import csv
import json
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from itertools import combinations

from baseline_lineage import DB, DEFAULT_PUZZLES
from benchmark_hybrid_graph import load_reference
from depth_graph_study import inverse, shallow
from discover_patterns import short_recipes, target_links
from first_solver import validate
from hybrid_graph_search import Construction, compile_changes, live_rollout, program_rules, rooted_rules


class Rewrite:
    def __init__(self, puzzle, incumbent):
        self.puzzle = puzzle
        self.starts = json.loads(puzzle['starting_values'])
        self.goals = sorted(json.loads(puzzle['targets']))
        self.limit = int(puzzle['value_limit'])
        self.original = {}
        for rule in program_rules(puzzle, incumbent):
            if rule[-1] not in self.starts:
                self.original.setdefault(rule[-1], rule)
        order = {v:i for i,v in enumerate(self.original)}
        self.order = sorted(self.goals, key=lambda t: order.get(t,-1))
        self.shallow, _ = shallow(self.starts, self.limit, 2)
        self.live = set(self.starts) | self.original.keys()
        self.pivots = list(dict.fromkeys(self.starts+list(self.original)))
        self.known = self.live | self.shallow.keys()
        self.plan = lru_cache(maxsize=None)(self.helper_plan)
        self.control = incumbent
        normalized = compile_changes(puzzle, list(self.original.values()), self.goals)
        if normalized is not None and len(normalized)<len(self.control):
            self.control = normalized
        normalized = self.compile(self.original, len(self.control))
        if normalized is not None:
            self.control = normalized

    def compile(self, graph, upper):
        try:
            steps = rooted_rules(self.starts, self.order, graph)
        except ValueError:  # An old value may itself depend on the replacement.
            return None
        if len(steps) >= upper:
            return None
        return compile_changes(self.puzzle, steps, self.goals)

    def helper_plan(self, v):
        if v in self.live:
            return ()
        if v in self.shallow:
            op,a,b,_ = self.shallow[v]
        else:
            for pivot in self.pivots:
                hit = next((rule for rule in inverse(v,pivot,self.limit)
                            if v not in rule[1:] and all(x in self.live for x in rule[1:])),None)
                if hit:
                    return ((*hit,v),)
            # Monotone fallback. Every recursive argument is smaller than v.
            base = 16
            if v<=base:
                op,a,b = ('+',v-1,1) if v%2 else ('+',v//2,v//2)
            elif v%base:
                op,a,b = '+',v-v%base,v%base
            else:
                op,a,b = '*',v//base,base
        return tuple(dict.fromkeys(self.plan(a)+self.plan(b)+((op,a,b,v),)))

    def patch(self, chain):
        supplied = set()
        path = []
        for op,a,b,v in chain:
            for x in (a,b):
                if x not in supplied:
                    path.extend(self.plan(x))
            supplied.add(v)
            path.append((op,a,b,v))
        return tuple(dict.fromkeys(path))

    def groups(self, data, which):
        result = []
        if which in ('delta','affine'):
            menu = defaultdict(list)
            cheap = short_recipes(self.starts,self.limit)
            for e in target_links(self.goals,cheap,self.limit):
                k,u,t,r = e['multiplier'],e['from'],e['to'],e['residual']
                if (k==1) != (which=='delta'):
                    continue
                chain = []
                if e['mode']=='before_multiply':
                    v = t//k
                    chain.append(('+' if r>0 else '-',u,abs(r)//k,v))
                    chain.append(('*',v,k,t))
                else:
                    if k!=1:
                        chain.append(('*',u,k,u*k))
                    if r:
                        chain.append(('+' if r>0 else '-',u*k,abs(r),t))
                menu[t].append(self.patch(chain))
            return [(None,menu)] if menu else []

        groups = data['relaxed'] if which=='factor' else data['translated']
        if which=='factor' and data['exact']:
            groups = data['exact']
        # GCD can have many equivalent divisors. Keep both broad and cheap choices.
        rank = sorted(groups,key=lambda g:(-len(g[2]),len(self.plan(g[0])),-g[0]))
        selected = list(dict.fromkeys((g[0],g[1]) for g in (groups[:4]+rank[:4])))
        for f,rem in selected:
            members = next(g[2] for g in groups if g[0]==f and g[1]==rem)
            menu = defaultdict(list)
            if which=='factor':
                centers = {t//f for t in members}
                for t in self.goals:
                    centers.update((t//f,t//f+1))
                for q in sorted(centers):
                    center = f*q
                    if q<2 or center>self.limit:
                        continue
                    for t in self.goals:
                        r = t-center
                        if r and abs(r) not in self.known:
                            continue
                        chain = [('*',f,q,center)]
                        if r:
                            chain.append(('+' if r>0 else '-',center,abs(r),t))
                        menu[t].append(self.patch(chain))
            # In either family two group members differ by an exact multiple of f.
            # Trying an existing target as an anchor also avoids materializing a costly residue.
            for u,t in combinations(members,2):
                q = (t-u)//f
                chain = [('*',f,q,t-u)] if q!=1 else []
                menu[t].append(self.patch(chain+[('+',u,t-u,t)]))
                menu[u].append(self.patch(chain+[('-',t,t-u,u)]))
            if rem:
                for t in members:
                    q = (t-rem)//f
                    if q>=2:
                        menu[t].append(self.patch([('*',f,q,t-rem),('+',t-rem,rem,t)]))
            result.append((f,menu))
        return result

    def run(self, data, which):
        best = self.control
        detail = None
        for factor,menu in self.groups(data,which):
            if not menu:
                continue
            graph = self.original.copy()
            local = self.control
            chosen = []
            menus = {}
            for t, choices in menu.items():
                menus[t] = sorted(set(choices),key=lambda p:(len(p),p))[:6]
            def try_set(items):
                nonlocal best,local,graph,chosen,detail
                trial = graph.copy()
                for t,path in items:
                    for rule in path:
                        if rule[-1]==t:
                            trial[t]=rule
                        elif rule[-1] not in self.starts:
                            trial.setdefault(rule[-1],rule)
                candidate = self.compile(trial,len(local))
                if candidate is None:
                    return
                local,graph = candidate,trial
                chosen = list(dict.fromkeys(chosen+[t for t,_ in items]))
                if len(local)<len(best):
                    best = local
                    detail = dict(factor=factor,targets=chosen.copy())

            cheapest = [(t,paths[0]) for t,paths in menus.items()]
            try_set(cheapest)
            for t,paths in menus.items():
                for path in paths:
                    try_set([(t,path)])
            # Two consumers may justify a helper that neither could afford alone.
            for pair in combinations(cheapest,2):
                try_set(pair)
        validate(self.puzzle,best)
        return dict(steps=len(best),detail=detail,program=best if detail else None)


def run_case(job):
    puzzle,data,own = job
    i = puzzle['id']
    out = {'route':data['route']}
    live,_ = live_rollout(Construction(puzzle),virtual=True)
    for name,initial in [('own',own),('live',live),('public',load_reference(i))]:
        if initial is None:
            continue
        engine = Rewrite(puzzle,initial)
        out[name] = dict(raw=len(initial),control=len(engine.control))
        for which in ('factor','residue','delta','affine'):
            out[name][which] = engine.run(data,which)
    return i,out


if __name__=='__main__':
    rows = json.loads(DB.with_name('factor_routing.json').read_text())['cases']
    with DEFAULT_PUZZLES.open() as f:
        puzzles = {p['id']:p for p in csv.DictReader(f)}
    with (DB.parent.parent/'experiments/anchor_scored_submission.csv').open() as f:
        own = {r['id']:json.loads(r['program']) for r in csv.DictReader(f)}
    by_route = defaultdict(list)
    for i,data in rows.items():
        by_route[data['route']].append(i)
    sample = []
    for name,ids in sorted(by_route.items()):
        rng = random.Random('factor-route-20261125-'+name)
        requested = 28 if name=='weak_factor' else 14
        sample.extend(ids if name=='factor' else rng.sample(ids,min(requested,len(ids))))
    with ProcessPoolExecutor(max_workers=4) as pool:
        out = dict(pool.map(run_case,[(puzzles[i],rows[i],own[i]) for i in sample]))
    DB.with_name('factor_routing_benchmark.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    print('verified',len(out),'puzzles')
