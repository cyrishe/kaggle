"""Shallow arithmetic closure, shared-factor construction and stochastic DAG repair."""
import json
import math
import random
from bisect import bisect_left
from collections import ChainMap, Counter, defaultdict
from itertools import combinations, combinations_with_replacement

from depth_graph_study import inverse, rules, shallow
from demand_pruning import targeted_plan
from export_50_baseline_cases import replay
from first_solver import validate
from probe_baseline_pair import compile_values


def program_rules(puzzle, program):
    return [(op, a, b, v) for _, _, a, op, _, b, _, v, _ in replay(puzzle, program)]


def rooted_rules(starts, targets, graph):
    built = set(starts)
    visiting = set()
    sequence = []

    def visit(value):
        if value in built:
            return
        if value in visiting:
            raise ValueError('cycle')
        visiting.add(value)
        rule = graph[value]
        visit(rule[1])
        visit(rule[2])
        visiting.remove(value)
        built.add(value)
        sequence.append(rule)

    for target in targets:
        visit(target)
    return sequence


def compile_changes(puzzle, sequence, targets):
    try:
        return compile_values(puzzle, sequence, targets)
    except ValueError as err:
        if str(err) == 'register budget exceeded':
            return None
        raise


class Construction:
    def __init__(self, puzzle):
        self.puzzle = puzzle
        self.starts = json.loads(puzzle['starting_values'])
        self.targets = sorted(json.loads(puzzle['targets']))
        self.limit = int(puzzle['value_limit'])
        self.shallow, self.layer_counts = shallow(self.starts, self.limit, 2)
        self.common = Counter(math.gcd(a, b) for a, b in combinations(self.targets, 2))
        self.common.pop(1, None)
        self.catalog = defaultdict(list)
        self.groups = []
        self.candidates = []

    def offer(self, rule):
        if rule not in self.catalog[rule[3]]:
            self.catalog[rule[3]].append(rule)

    def construct(self):
        bases = sorted({min(self.limit, b) for b in (2, 4, 8, 16, 32)} |
                       {b for b, _ in self.common.most_common(3) if 2 <= b <= 64} |
                       {b for b in self.starts if 2 <= b <= 64})
        for base in bases:
            graph = {}
            def build(n):
                if n in graph or n in self.starts:
                    return
                if n in self.shallow:
                    rule = self.shallow[n]
                elif n < base or n == base:
                    rule = ('+', n-1, 1, n) if n % 2 else ('+', n//2, n//2, n)
                else:
                    q, r = divmod(n, base)
                    if r == 0:
                        rule = ('*', q, base, n)
                    elif r > base//2 and n+base-r <= self.limit:
                        rule = ('-', n+base-r, base-r, n)
                    else:
                        rule = ('+', n-r, r, n)
                # The rounded-up product has an exact division by this same base.
                graph[n] = rule
                build(rule[1])
                build(rule[2])
                self.offer(rule)

            for t in self.targets:
                build(t)
            seq = rooted_rules(self.starts, self.targets, graph)
            program = compile_changes(self.puzzle, seq, self.targets)
            if program is not None:
                self.candidates.append(program)
            # Keep alternative recipes and their ancestors as virtual helpers.
            for factor, _ in self.common.most_common(16):
                group = []
                for t in self.targets:
                    if factor < t and t % factor == 0:
                        build(factor)
                        build(t//factor)
                        group.append(('*', t//factor, factor, t))
                for rule in group:
                    self.offer(rule)
                if group and group not in self.groups:
                    self.groups.append(group)
            for t in self.targets:
                neighbors = sorted((u for u in self.targets if u != t), key=lambda u: abs(t-u))[:3]
                for u in neighbors:
                    gap = abs(t-u)
                    build(gap)
                    self.offer(('+', u, gap, t) if u<t else ('-', u, gap, t))
        if not self.candidates:
            from first_solver import build
            fallback = build(self.puzzle, 2)
            validate(self.puzzle, fallback)
            self.candidates.append(fallback)
        return min(self.candidates, key=len)


def graph_search(model, initial, random_seed=None, attempts=96):
    """Keep complete legal programs; alternative ancestors are materialized on demand."""
    starts, goals = model.starts, model.targets
    original = program_rules(model.puzzle, initial)
    graph = {v: options[0] for v, options in model.catalog.items()}
    for rule in reversed(original):
        graph[rule[3]] = rule
    best = initial
    best_graph = dict(graph)
    current = len(best)
    active = {r[3] for r in original}
    rng = random.Random(random_seed)
    trials = improvements = 0

    def evaluate(moves, plateau=False):
        nonlocal current, best, best_graph, active, improvements, trials
        old = {r[3]: graph[r[3]] for r in moves}
        graph.update((r[3], r) for r in moves)
        trials += 1
        try:
            seq = rooted_rules(starts, goals, graph)
        except ValueError:
            seq = None
        if seq is not None and len(seq) <= current + int(plateau):
            candidate = compile_changes(model.puzzle, seq, goals)
            if candidate is not None and (len(candidate)<current or plateau):
                current = len(candidate)
                active = {r[3] for r in seq}
                if current < len(best):
                    improvements += 1
                    best, best_graph = candidate, dict(graph)
                return
        graph.update(old)

    if random_seed is None:
        for group in model.groups:
            evaluate(group)
        for node in sorted(graph, reverse=True):
            if node in active:
                for option in model.catalog.get(node, []):
                    if option != graph[node]:
                        evaluate([option])
    else:
        for i in range(attempts):
            if i and i % 24 == 0:
                graph = dict(best_graph)
                active = {r[3] for r in rooted_rules(starts, goals, graph)}
                current = len(best)
            if model.groups and rng.random() < 0.25:
                moves = rng.choice(model.groups)
            else:
                nodes = sorted(v for v in active if len(model.catalog.get(v, ())) > 1)
                if not nodes:
                    continue
                chosen = rng.sample(nodes, min(len(nodes), rng.choice((1, 1, 2, 3))))
                moves = [rng.choice([r for r in model.catalog[v] if r != graph[v]] or [graph[v]]) for v in chosen]
            evaluate(moves, plateau=rng.random()<0.25)
    return best, dict(trials=trials, improvements=improvements)


def local_repair(puzzle, initial, seed, budget=64, reschedule=False):
    """Remove a private ancestor cone; match inverse operations against a shallow forward pool."""
    starts = json.loads(puzzle['starting_values'])
    goals = json.loads(puzzle['targets'])
    limit = int(puzzle['value_limit'])
    rng = random.Random(seed)
    program = initial
    wins = []
    tried = set()
    for _ in range(budget):
        trace = program_rules(puzzle, program)
        # First producer per value is sufficient for a proposed reschedule.
        graph = {}
        for rule in trace:
            if rule[3] not in starts:
                graph.setdefault(rule[3], rule)
        ordered = list(graph)
        index = {v:i for i,v in enumerate(ordered)}
        consumers = Counter(goals)
        for op,a,b,v in graph.values():
            consumers.update({a,b})
        def private(v, removed):
            for a in set(graph[v][1:3]):
                if a in graph and consumers[a] == 1 and a not in removed:
                    removed.add(a)
                    private(a, removed)
        options = []
        for v in ordered:
            if v in tried:
                continue
            removed = {v}
            private(v, removed)
            if len(removed) >= 2:
                options.append((len(removed), v, removed))
        if not options:
            break
        options.sort(reverse=True)
        _, goal, removed = rng.choice(options if rng.random()<0.35 else options[:12])
        tried.add(goal)
        pos = index[goal]
        survivors = [v for v in ordered[:pos] if v not in removed]
        if reschedule:
            blocked = set(removed)
            for v in ordered[pos+1:]:
                if any(parent in blocked for parent in graph[v][1:3]):
                    blocked.add(v)
                else:
                    survivors.append(v)
        leaves = list(dict.fromkeys(starts + survivors))
        # Bias toward reusable and dividing operands, with room for unexpected pairs.
        ranked = sorted(survivors, key=lambda v:(goal%v!=0, -consumers[v], -index[v]))
        extras = [v for v in survivors if v not in ranked[:16]]
        pivots = sorted(set(starts + ranked[:16] + rng.sample(extras, min(16,len(extras)))))
        known = dict.fromkeys(leaves)
        for a,b in combinations_with_replacement(pivots, 2):
            for op,x,y,v in rules(a,b,limit):
                if 0<v<=limit:
                    known.setdefault(v,(op,x,y,v))
        replacements = []
        if goal in known and known[goal] is not None:
            replacements.append([known[goal]])
        for a in known:
            for op,x,y in inverse(goal,a,limit):
                if x not in known or y not in known or goal in (x,y):
                    continue
                new = [known[k] for k in dict.fromkeys((x,y)) if known[k] is not None]
                new.append((op,x,y,goal))
                if len(new)<len(removed):
                    replacements.append(new)
                    if len(replacements)>=12:
                        break
            if len(replacements)>=12:
                break
        for patch in sorted(replacements, key=len):
            if reschedule:
                updated = dict(graph)
                updated.update((r[3], r) for r in patch)
                roots = [v for v in ordered if v in goals]
                seq = rooted_rules(starts, roots, updated)
            else:
                seq = [graph[v] for v in ordered[:pos] if v not in removed] + patch + [graph[v] for v in ordered[pos+1:]]
            candidate = compile_changes(puzzle, seq, goals)
            if candidate is not None and len(candidate)<len(program):
                wins.append(dict(root=goal, removed=len(removed), patch=patch, before=len(program), after=len(candidate)))
                program = candidate
                tried.clear()
                break
    return program, wins


def live_rollout(model, seed=None, virtual=False, policy='jitter', extra_layer=None,
                 correction_mode=None, walk=None):
    """Bounded reverse beam over near products; emit each chosen DAG into live registers."""
    puzzle, goals = model.puzzle, model.targets[:]
    starts, limit = model.starts, model.limit
    rng = random.Random(seed)
    if seed is not None:
        # Keep similar magnitudes together but vary the target order within blocks.
        for pos in range(0, len(goals), 4):
            block = goals[pos:pos+4]
            rng.shuffle(block)
            goals[pos:pos+4] = block
    slots = {v:i for i,v in enumerate(starts)}
    program = []
    covered = set(starts)
    if walk is not None and walk.prefix is not None:
        program = list(walk.prefix.program)
        slots = dict(walk.prefix.slots)
        covered.update(walk.prefix.hits)
    left = set(goals) - covered
    support = {}
    for v, rule in model.shallow.items():
        support[v] = set() if rule is None else support[rule[1]] | support[rule[2]] | {v}
    cheap = sorted(support, key=lambda v:(len(support[v]), v))
    shallow_costs = {v:len(nodes) for v,nodes in support.items()}
    common = [g for g,_ in model.common.most_common(10)]
    metrics = Counter()

    for target in goals:
        if target in covered:
            continue
        live = set(slots)
        # Retain start values while emitting, so any virtual F2 leaf can be recovered.
        if extra_layer is None:
            recipes = dict(model.shallow)
            costs = shallow_costs.copy()
        else:
            # Share the static layer across targets. Dynamic helpers and fallback
            # recipes take precedence and are local to this register snapshot.
            recipes = ChainMap({}, model.shallow, extra_layer[0])
            costs = ChainMap({}, shallow_costs, extra_layer[1])
        one_step = {}
        if virtual:
            for a,b in combinations_with_replacement(sorted(live), 2):
                for op,x,y,v in rules(a,b,limit):
                    if 0<v<=limit and v not in live and v not in one_step:
                        one_step[v] = (op,x,y,v)
            recipes.update(one_step)
            costs.update(dict.fromkeys(one_step, 1))
        product_partners = sorted(live | set(one_step))
        def fallback(v):
            if v in live or v in recipes:
                return
            if v <= 16:
                rule = ('+', v-1, 1, v) if v%2 else ('+', v//2, v//2, v)
            else:
                q, r = divmod(v, 16)
                if not r:
                    rule = ('*', q, 16, v)
                elif r>8 and v+16-r<=limit:
                    rule = ('-', v+16-r, 16-r, v)
                else:
                    rule = ('+', v-r, r, v)
            recipes[v] = rule
            fallback(rule[1])
            fallback(rule[2])

        def leaf(v):
            if v in live:
                return []
            fallback(v)
            return rooted_rules(live, [v], recipes)

        def merge(*parts):
            seen = set()
            out = []
            for part in parts:
                for rule in part:
                    if rule[3] not in seen:
                        out.append(rule)
                        seen.add(rule[3])
            return out

        anchors = sorted((live | set(common) | set(cheap[:48]) |
                          {v for v in (2,4,8,16,32,64) if v <= limit}) - {1})
        reuse = {v:sum(t%v == 0 for t in left) for v in anchors} if policy=='shared' else {}
        memo = {}
        def search(n, depth):
            key = n, depth
            if key in memo:
                return memo[key]
            best = leaf(n)
            if len(best)<=1:
                return best
            for a in live:
                for op,x,y in inverse(n, a, limit):
                    if x in live and y in live:
                        return [(op,x,y,n)]
            if virtual:
                for a in anchors:
                    for op,x,y in inverse(n,a,limit):
                        if x == n or y == n or (x not in live and x not in costs) or (y not in live and y not in costs):
                            continue
                        trial = merge(leaf(x), leaf(y), [(op,x,y,n)])
                        if len(trial)<len(best):
                            best = trial
                    if depth != 3 or a>n:
                        continue
                    idx = bisect_left(product_partners, (n+a-1)//a)
                    for b in product_partners[max(0,idx-2):idx+2]:
                        product = a*b
                        diff = abs(n-product)
                        if product>limit or not diff or (diff not in costs and diff not in live):
                            continue
                        end = ('+' if product<n else '-', product, diff, n)
                        trial = merge(leaf(a),leaf(b),leaf(diff),[('*',a,b,product),end])
                        if len(trial)<len(best):
                            best = trial
                if len(best)<=2:
                    memo[key] = best
                    return best
            branches = []
            for base in anchors:
                if base >= n:
                    continue
                q0,r0 = divmod(n,base)
                variants = [(q0,r0)]
                if r0 and n+base-r0 <= limit:
                    variants.append((q0+1,r0-base))
                for q,r in variants:
                    if q>=n or (r and abs(r) not in live and abs(r) not in costs and abs(r)>16):
                        continue
                    # Count the immediate work, then estimate the unfinished quotient.
                    r_cost = 0 if not r or abs(r) in live else costs.get(abs(r), 3)
                    b_cost = 0 if base in live else costs.get(base, 5)
                    q_cost = 0 if q in live else costs.get(q, q.bit_length()/3)
                    priority = b_cost + q_cost + r_cost + bool(r)
                    if policy=='shared':
                        priority -= min(1.75, 0.35*math.log2(1+reuse[base]))
                    elif policy=='residual' and (not r or abs(r) in live):
                        priority -= 0.9
                    if seed is not None and policy!='order':
                        priority += rng.uniform(-1.25,1.25)
                    branches.append((priority,base,q,r))
            branches.sort()
            for _,base,q,r in branches[:3]:
                metrics['branches'] += 1
                sub = search(q,depth-1) if depth else leaf(q)
                product = base*q
                pieces = [sub,leaf(base),[('*',base,q,product)]]
                if r:
                    pieces.extend([leaf(abs(r)), [('+' if r>0 else '-',product,abs(r),n)]])
                trial = merge(*pieces)
                if len(trial)<len(best):
                    best = trial
            memo[key] = best
            return best

        plan = search(target, 3)
        if correction_mode is not None:
            plan = targeted_plan(target,left,live,product_partners,one_step,costs,limit,
                                 leaf,merge,search,plan,metrics,correction_mode=='joint')
        needed = Counter(a for rule in plan for a in rule[1:3])
        # Rank resident values by known future use before overwriting any register.
        def usefulness(v):
            return (sum(t%v==0 for t in left), v<=32, v in model.common, -v.bit_length())
        for op,a,b,v in plan:
            needed[a] -= 1
            needed[b] -= 1
            if v in slots:
                continue
            if walk is not None and len(program)+len(left)>walk.cap:
                metrics['cutoff'] = 1
                metrics['spent'] = len(program)
                metrics['covered'] = len(goals)-len(left)
                return None, dict(metrics)
            i,j = slots[a], slots[b]
            if len(slots)<int(puzzle['registers']):
                dest = min(set(range(int(puzzle['registers']))) - set(slots.values()))
            else:
                eligible = [x for x in slots if x not in starts and not needed[x]]
                if not eligible:
                    return None, dict(metrics)
                victim = min(eligible,key=usefulness)
                dest = slots.pop(victim)
            program.append([op,i,j,dest])
            slots[v] = dest
            covered.add(v)
            left.discard(v)
            if walk is not None and not left:
                break
        if walk is not None:
            walk.record(program,slots,set(goals)-left)
    validate(puzzle, program)
    return program, dict(metrics)


def shared_helper_repair(puzzle, initial, seed, rounds=2):
    """Jointly rewire every direct user of a helper through an alternate numeric bridge."""
    starts = json.loads(puzzle['starting_values'])
    goals = set(json.loads(puzzle['targets']))
    limit = int(puzzle['value_limit'])
    rng = random.Random(seed)
    best = program = initial
    wins = []
    plateaus = set()
    for _ in range(rounds):
        graph = {}
        for rule in program_rules(puzzle, program):
            if rule[3] not in starts:
                graph.setdefault(rule[3], rule)
        users = defaultdict(set)
        for child, (_,a,b,_) in graph.items():
            users[a].add(child)
            users[b].add(child)
        roots = [v for v in graph if v in goals]
        plateaus.add(tuple(rooted_rules(starts, roots, graph)))
        helpers = [v for v in graph if v not in goals and 2<=len(users[v])<=5]
        rng.shuffle(helpers)
        accepted = False
        for old in helpers:
            children = sorted(users[old])
            blocked = {old}
            for value, rule in graph.items():
                if any(a in blocked for a in rule[1:3]):
                    blocked.add(value)
            safe = (set(graph) | set(starts)) - blocked
            def recipes_for(value):
                for a in sorted(safe):
                    for op,x,y in inverse(value,a,limit):
                        if x in safe and y in safe:
                            yield (op,x,y,value)
            alternatives = []
            common = None
            for child in children:
                demand = {}
                for a in sorted(safe):
                    for op,x,y in inverse(child,a,limit):
                        sibling = y if x==a else x
                        if 0<sibling<=limit and sibling not in children and (common is None or sibling in common):
                            demand.setdefault(sibling,(op,x,y,child))
                alternatives.append(demand)
                common = set(demand)
            # First try removing the old helper with no shared replacement at all.
            direct = [next(recipes_for(child), None) for child in children]
            proposals = [(None,direct)] if all(direct) else []
            gcd = math.gcd(*children)
            bridges = sorted(common or (), key=lambda b:(b not in safe, b!=gcd, b))
            for bridge in bridges[:16]:
                new = None if bridge in safe else next(recipes_for(bridge), None)
                if new is not None or bridge in safe:
                    proposals.append((new,[d[bridge] for d in alternatives]))
            for new, ruleset in proposals:
                updated = dict(graph)
                if new is not None:
                    updated[new[3]] = new
                updated.update((r[3],r) for r in ruleset)
                sequence = rooted_rules(starts, roots, updated)
                if len(sequence)>len(program):
                    continue
                candidate = compile_changes(puzzle, sequence, sorted(goals))
                if candidate is None or len(candidate)>len(program):
                    continue
                signature = tuple(sequence)
                if len(candidate)==len(program):
                    if signature in plateaus or rng.random()>=0.025:
                        continue
                    plateaus.add(signature)
                program = candidate
                if len(program)<len(best):
                    wins.append(dict(old=old, children=children, helper=new, rules=ruleset,
                                     before=len(best), after=len(program)))
                    best = program
                accepted = True
                break
            if accepted:
                break
        if not accepted:
            break
    return best, wins
