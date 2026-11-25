"""Randomized greedy construction and a matched search around elite arithmetic DAGs."""
import argparse
import csv
import json
import math
import random
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from benchmark_hybrid_graph import DEFAULT_PUZZLES, ROOT, load_reference
from depth_graph_study import inverse
from discover_patterns import short_recipes, target_links
from factor_quotient_solver import schedule
from factor_routing import exact_groups
from first_solver import validate
from hybrid_graph_search import Construction, compile_changes, live_rollout, program_rules, rooted_rules

DIAGNOSTICS = ['scored_0253','scored_0667','scored_0810','scored_0035','scored_0307','scored_0755']
SEEDS = [4101,4102,4103]


def normalized(rule):
    op,a,b,v = rule
    return (op,b,a,v) if op in ('+','*') and b<a else (op,a,b,v)


def signature(steps):
    return tuple(sorted(steps))


def graph_of(rules,starts):
    graph = {}
    for rule in rules:
        if rule[3] not in starts:
            graph.setdefault(rule[3],normalized(rule))
    return graph


def missing(template,ready):
    needed = {template[-1][-1]}
    patch = []
    for op,a,b,v in reversed(template):
        if v not in ready and v in needed:
            patch.append((op,a,b,v))
            needed.update((a,b))
    patch.reverse()
    return patch


class Recipes:
    def __init__(self,p,joins=False):
        self.p = p
        model = Construction(p)
        self.goals = tuple(model.targets)
        self.goalset = set(self.goals)
        self.starts = set(model.starts)
        self.limit = model.limit
        # Only the puzzle is used to build this dictionary. The public program is read for scoring later.
        programs = []
        for index in range(7):
            seed = 71419+index if index else None
            prog,_ = live_rollout(model,seed,virtual=True,policy=('order','residual','shared')[index%3])
            if prog is not None:
                programs.append(prog)
        groups = exact_groups(self.goals,max(100,max(self.starts)+1))
        seen = set()
        for f,_,members in groups:
            if len(members)<3 or len(seen)>=2:
                break
            if members in seen:
                continue
            seen.add(members)
            proxy_goals = list(dict.fromkeys([f]+[g//f for g in members]+[g for g in self.goals if g not in members]))
            proxy = dict(p,targets=json.dumps(proxy_goals))
            proxy_program,_ = live_rollout(Construction(proxy),virtual=True)
            if proxy_program is not None:
                lifted = schedule(p,program_rules(proxy,proxy_program),
                                  {t:('*',f,t//f,t) for t in members},[self.goals])
                if lifted is not None:
                    programs.append(lifted)
        self.seed_steps = [len(x) for x in programs]
        self.options = defaultdict(list)
        graphs = [graph_of(program_rules(p,prog),self.starts) for prog in programs]
        if not graphs:
            raise ValueError('no construction for menu')
        self.seeds = []
        for graph in graphs:
            # Only retain a normalized graph if its compiled program has the
            # stated cost; raw programs can compute the same value more than once.
            graph_prog = self.finish(list(graph.values()),4096)
            if graph_prog is not None:
                self.seeds.append(graph_prog)
        def add(v,path):
            rules = tuple(normalized(r) for r in path)
            if rules and rules not in self.options[v]:
                self.options[v].append(rules)
        self.backbones = []
        for graph in graphs:
            target_paths = {}
            for v in graph:
                seq = rooted_rules(self.starts,[v],graph)
                add(v,seq)
                if v in self.goalset:
                    target_paths[v] = tuple(normalized(r) for r in seq)
            self.backbones.append(target_paths)
        requests = Counter(v for graph in graphs for v in graph)
        requests.update({t:len(graphs)+1 for t in self.goals})
        cheap = model.shallow
        ranked_cheap = sorted(cheap,key=lambda v:(v not in self.starts,v))
        largest = max(ranked_cheap)
        # Direct lookup at depth two. Reverse-join both operands in depth two
        # to recover depth-three plans on demand for the most frequent requests.
        shallow_paths = {}
        def path(v):
            if v not in shallow_paths:
                shallow_paths[v] = tuple(rooted_rules(self.starts,[v],cheap))
            return shallow_paths[v]
        for v in requests:
            if v in cheap:
                add(v,path(v))
        for v,_ in requests.most_common(len(self.goals)+48):
            if v in cheap or v>max(largest**2,2*largest):
                continue
            candidates = []
            for a in ranked_cheap:
                for op,x,y in inverse(v,a,self.limit):
                    if v in (x,y) or x not in cheap or y not in cheap:
                        continue
                    recipe = tuple(dict.fromkeys(path(x)+path(y)))+((op,x,y,v),)
                    if recipe not in candidates:
                        candidates.append(recipe)
                if len(candidates)>=12:
                    break
            for recipe in sorted(candidates,key=len)[:2]:
                add(v,recipe)
        # Each affine link is also a complete recipe for t, including the source target.
        cheap_seq = short_recipes(model.starts,self.limit)
        for edge in target_links(self.goals,cheap_seq,self.limit):
            u,k,r,t = (edge[x] for x in ('from','multiplier','residual','to'))
            if u in self.starts:
                prefixes = [()]
            else:
                prefixes = sorted(self.options[u],key=len)[:2]
            for prefix in prefixes:
                rules = list(prefix)
                rules.extend(cheap_seq[k] if k!=1 else ())
                if edge['mode']=='before_multiply':
                    rules.extend(cheap_seq[abs(r)//k])
                    rules.extend([('+' if r>0 else '-',u,abs(r)//k,t//k),('*',t//k,k,t)])
                else:
                    if k!=1:
                        rules.append(('*',u,k,u*k))
                    if r:
                        rules.extend(cheap_seq[abs(r)])
                        rules.append(('+' if r>0 else '-',u*k,abs(r),t))
                graph = graph_of(rules,self.starts)
                if t not in self.starts:
                    add(t,rooted_rules(self.starts,[t],graph))
        if joins:
            self.add_joins(requests,cheap,path,add)
        # Shorter standalone recipes first, with duplicates of the same rule set removed.
        for v,options in self.options.items():
            unique = {}
            for seq in options:
                unique.setdefault(signature(seq),seq)
            self.options[v] = sorted(unique.values(),key=len)
        self.last_rules = {v:{seq[-1] for seq in paths} for v,paths in self.options.items()}
        self.support = Counter()
        for t in self.goals:
            self.support.update({r[3] for seq in self.options[t] for r in seq})

    def add_joins(self,requests,cheap,shallow_path,add):
        # Cross-connect two operands from different source DAGs. Hold lookup costs
        # fixed throughout this pass so newly added recipes cannot bias later roots.
        sources = {v:min(paths,key=len) for v,paths in self.options.items() if paths}
        known = set(sources) | set(cheap)
        pivots = sorted(set(sources) | self.starts)
        def source(v):
            if v not in cheap:
                return sources[v]
            shortest = shallow_path(v)
            alt = sources.get(v)
            return alt if alt and len(alt)<len(shortest) else shortest
        for v,_ in requests.most_common(len(self.goals)+128):
            if v in self.starts:
                continue
            seen = {seq[-1] for seq in self.options[v]}
            ranked = []
            for a in pivots:
                for op,x,y in inverse(v,a,self.limit):
                    rule = normalized((op,x,y,v))
                    if v in (x,y) or x not in known or y not in known or rule in seen:
                        continue
                    seen.add(rule)
                    left,right = source(x),source(y)
                    if any(r[3]==v for r in left+right):
                        continue
                    cost = len(left)+len(right)
                    score = cost-0.5*min(6,requests.get(x,0))-0.5*min(6,requests.get(y,0))
                    ranked.append((score,rule,left,right))
            for _,rule,left,right in sorted(ranked,key=lambda c:(c[0],c[1]))[:8]:
                merged = graph_of((*left,*right,rule),self.starts)
                add(v,rooted_rules(self.starts,[v],merged))

    def construct(self,rng,cap):
        ready = self.starts.copy()
        sequence = []
        remaining = [v for v in self.goals if v not in ready]
        backbone = rng.choice(self.backbones)
        loyalty = rng.choice((0.0,0.5,0.85,0.98))
        while remaining:
            # Randomized target shortlist. Within it prefer cheap marginal instructions
            # and helpers shared by templates of other targets.
            choices = []
            for t in rng.sample(remaining,min(3,len(remaining))):
                options = self.options[t]
                sampled = ([backbone[t]] if rng.random()<loyalty else
                           [options[0]]+rng.sample(options[1:],min(3,len(options)-1)))
                for opt in sampled:
                    patch = missing(opt,ready)
                    hits = sum(v in self.goalset for *_,v in patch)
                    reuse = sum(min(self.support[v]-1,5) for *_,v in patch)
                    score = (len(patch)-0.10*reuse)/max(1,hits)
                    choices.append((score,patch))
            choices.sort(key=lambda c:c[0])
            shortlist = [patch for score,patch in choices[:4] if score<=choices[0][0]+2]
            patch = rng.choice(shortlist)
            sequence.extend(patch)
            ready.update(r[3] for r in patch)
            remaining = [g for g in remaining if g not in ready]
            if len(sequence)+len(remaining)>cap:
                return None
        return self.finish(sequence,cap)

    def finish(self,seq,cap):
        if len(seq)>cap:
            return None
        prog = compile_changes(self.p,seq,self.goals)
        return (tuple(seq),prog) if prog is not None and len(prog)<=cap else None

    def change(self,parent,rng,cap):
        seq,_ = parent
        graph = {r[3]:r for r in seq}
        choices = [v for v in graph if self.last_rules.get(v,set())-{graph[v]}]
        if not choices:
            return None
        pivot = rng.choice(choices)
        # Sometimes perturb a pair of connected choices in one proposal.
        pivots = [pivot]
        if rng.random()<0.35:
            neighbors = [v for v in choices if v in graph[pivot][1:3] or pivot in graph[v][1:3]]
            if neighbors:
                pivots.append(rng.choice(neighbors))
        for v in pivots:
            alternatives = [path for path in self.options[v] if path[-1]!=graph[v]]
            if not alternatives:
                continue
            path = rng.choice(alternatives)
            for rule in path[:-1]:
                graph.setdefault(rule[3],rule)
            graph[v] = path[-1]
        try:
            changed = rooted_rules(self.starts,self.goals,graph)
        except ValueError:
            return None
        return self.finish(changed,cap)


def retain(elites,candidate):
    if candidate is None:
        return
    seq,prog = candidate
    if len(elites)>=5 and len(prog)>=len(elites[-1][1]):
        return
    key=signature(seq)
    if any(key==signature(old) for old,_ in elites):
        return
    elites.append(candidate)
    elites.sort(key=lambda x:len(x[1]))
    del elites[5:]


def compare(book,seed,cap,keep_seeds):
    start = time.perf_counter()
    pool = []
    signatures = set()
    first3 = set()
    completed = 0
    curve = {}
    for i in range(500):
        result = book.construct(random.Random(seed*10000+i),cap)
        if result is not None:
            completed+=1
            signatures.add(signature(result[0]))
            first3.add(result[0][:3])
            retain(pool,result)
        if i+1 in (50,100,250,500):
            curve[i+1] = len(pool[0][1]) if pool else None
    explore_time = time.perf_counter()-start
    arms = {}
    base = pool.copy()
    if keep_seeds:
        for result in book.seeds:
            if len(result[1])<=cap:
                retain(base,result)
    for arm in ('fresh','hill','elite'):
        start = time.perf_counter()
        pool = base.copy()
        current = None
        recent = deque(maxlen=12)
        moves = Counter()
        witness = None
        for j in range(200):
            rng = random.Random(seed*10000+500+j)
            if arm=='fresh' or not pool:
                result = book.construct(rng,cap)
                moves['fresh']+=1
            else:
                if j%12==0 or current is None:
                    current = rng.choice(pool)
                    recent.clear()
                    recent.append(signature(current[0]))
                result = book.change(current,rng,cap)
                moves['local']+=1
                if result is not None:
                    cost = len(result[1])-len(current[1])
                    if cost<0 and (witness is None or cost<witness['delta']):
                        old = {r[3]:r for r in current[0]}
                        new = {r[3]:r for r in result[0]}
                        witness = dict(delta=cost,before=len(current[1]),after=len(result[1]),
                                       replacements=[(r,new[v]) for v,r in old.items() if v in new and new[v]!=r],
                                       removed=sorted(old.keys()-new.keys()),added=sorted(new.keys()-old.keys()))
                    key = signature(result[0])
                    temperature = 2.0*(0.25**((j%12)/11))
                    if key not in recent and (cost<=0 or
                            (arm=='elite' and rng.random()<math.exp(-cost/temperature))):
                        moves['uphill' if cost>0 else 'level' if cost==0 else 'downhill']+=1
                        recent.append(key)
                        current = result
            if result is not None:
                moves['valid']+=1
                retain(pool,result)
        best = pool[0][1] if pool else None
        if best is not None:
            validate(book.p,best)
        arms[arm] = dict(best=len(best) if best is not None else None, moves=dict(moves),
                         seconds=round(time.perf_counter()-start,3),program=best,witness=witness)
    return dict(seed=seed,cap=cap,curve=curve,complete=completed,unique=len(signatures),
                archive_at_500=len(base[0][1]) if base else None,
                first3=len(first3),initial_seconds=round(explore_time,3),arms=arms)


def run(job):
    ident,p,seeds,diagnose,joins,keep = job
    start = time.perf_counter()
    book = Recipes(p,joins)
    setup = round(time.perf_counter()-start,3)
    caps = [150]
    if diagnose and min(book.seed_steps)>150:
        caps.append(min(book.seed_steps))
    rows = [compare(book,seed,cap,keep) for cap in caps for seed in seeds]
    public = len(load_reference(ident))
    print(ident,min(book.seed_steps),[(r['cap'],r['complete'],r['arms']['fresh']['best'],r['arms']['elite']['best']) for r in rows],flush=True)
    return ident,dict(goals=len(book.goals),menu_source_lengths=book.seed_steps,setup_seconds=setup,
                      public=public,runs=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',nargs='+')
    parser.add_argument('--seeds',type=int,nargs='+',default=SEEDS)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--diagnostic-cap',action='store_true')
    parser.add_argument('--joins',action='store_true',help='Add exact reverse joins between numeric DAGs.')
    parser.add_argument('--keep-seeds',action='store_true',help='Also archive the feasible menu-source graphs.')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/monte_carlo_recipe_search.json')
    args=parser.parse_args()
    with DEFAULT_PUZZLES.open() as file:
        puzzles={p['id']:p for p in csv.DictReader(file)}
    ids=args.ids or DIAGNOSTICS+random.Random(457210).sample(sorted(set(puzzles)-set(DIAGNOSTICS)),4)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows=dict(pool.map(run,[(i,puzzles[i],args.seeds,args.diagnostic_cap,args.joins,args.keep_seeds) for i in ids]))
    args.output.write_text(json.dumps(rows,separators=(',',':'))+'\n')
