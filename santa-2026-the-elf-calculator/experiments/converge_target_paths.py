"""Shorten a merged arithmetic DAG by rewiring internal results and sharing missing operands."""
import heapq
import json
import random
from bisect import bisect_left
from collections import Counter, defaultdict
from itertools import combinations, combinations_with_replacement

from depth_graph_study import inverse, rules
from first_solver import validate
from hybrid_graph_search import compile_changes, program_rules, rooted_rules


def schedule(starts, goals, graph, rank):
    """Reachability from requested outputs, then stable topological order (cycles fail)."""
    used = set()
    stack = list(goals)
    while stack:
        v = stack.pop()
        if v not in starts and v not in used:
            used.add(v)
            stack.extend(graph[v][1:3])
    users = defaultdict(list)
    counts = {}
    ready = []
    for v in used:
        parents = set(graph[v][1:3]) - starts
        counts[v] = len(parents)
        for p in parents:
            users[p].append(v)
        if not parents:
            heapq.heappush(ready, (rank.get(v, -1), v))
    seq = []
    while ready:
        _, v = heapq.heappop(ready)
        seq.append(graph[v])
        for t in users[v]:
            counts[t] -= 1
            if not counts[t]:
                heapq.heappush(ready, (rank.get(t, -1), t))
    return seq if len(seq) == len(used) else None


class Context:
    def __init__(self, starts, goals, seq, limit):
        self.starts, self.goals, self.limit = starts, goals, limit
        self.graph = {r[3]: r for r in seq}
        self.values = sorted(starts | self.graph.keys())
        self.anc = {v: 0 for v in starts}
        self.bit = {r[3]: 1 << i for i, r in enumerate(seq)}
        self.rank = {r[3]: i for i, r in enumerate(seq)}
        self.serves = {r[3]: 0 for r in seq}
        self.users = defaultdict(set)
        for i, v in enumerate(goals):
            if v not in starts:
                self.serves[v] = 1 << i
        for _, a, b, v in seq:
            self.anc[v] = self.bit[v] | self.anc[a] | self.anc[b]
            self.users[a].add(v)
            self.users[b].add(v)
        self.private = {v: 0 for v in self.graph}
        # An ancestor is private to v if every path from it to an output passes v.
        dominators = {}
        ordered = list(self.graph)
        for _, a, b, v in reversed(seq):
            for p in {a,b} - starts:
                self.serves[p] |= self.serves[v]
            consumers = iter(self.users[v])
            common = 0 if v in goals else dominators[next(consumers)]
            for child in consumers:
                common &= dominators[child]
            dominators[v] = common | self.bit[v]
            while common:
                bit = common & -common
                self.private[ordered[bit.bit_length()-1]] |= self.bit[v]
                common ^= bit

    def single_rewrites(self, rng):
        proposals = []
        for a, b in combinations_with_replacement(self.values, 2):
            ancestors = self.anc[a] | self.anc[b]
            for rule in rules(a,b,self.limit):
                v = rule[3]
                if v not in self.graph or self.bit[v] & ancestors:
                    continue
                gain = (self.private[v] & ~ancestors).bit_count()
                if gain:
                    proposals.append((gain, rng.random(), rule))
        return sorted(proposals, reverse=True)

    def shared_rewrites(self, rng):
        # Gather near differences plus exact factors/quotients. Count a missing operand
        # once per distinct consumer; multiplicity from equivalent expressions buys nothing.
        need = defaultdict(dict)
        targets = sorted(self.graph, key=lambda v: (-self.private[v].bit_count(), v))[:140]
        for v in targets:
            ix = bisect_left(self.values,v)
            neighbors = set(self.values[max(0,ix-12):ix+13]) | set(self.values[:12])
            def offer(h, rule, other):
                if 0 < h <= self.limit and h not in self.anc and not (self.anc[other] & self.bit[v]):
                    old = need[h].get(v)
                    weight = (self.private[v] & ~self.anc[other]).bit_count()
                    if old is None or weight > old[0]:
                        need[h][v] = (weight, rule)
            for a in sorted(neighbors):
                if a < v:
                    offer(v-a, ('+', a, v-a, v), a)
                elif a > v:
                    offer(a-v, ('-', a, a-v, v), a)
            for a in self.values:
                if v != a and v % a == 0:
                    offer(v//a, ('*', a, v//a, v), a)
                if a != v and a % v == 0:
                    offer(a//v, ('/', a, a//v, v), a)
        need = {h: out for h, out in need.items() if len(out) >= 2}
        if not need:
            return []
        born = defaultdict(list)
        for a,b in combinations_with_replacement(self.values,2):
            for rule in rules(a,b,self.limit):
                if rule[3] in need:
                    born[rule[3]].append(rule)
        proposals = []
        for h, constructors in born.items():
            consumers = list(need[h].items())
            for make in sorted(constructors, key=lambda r: (self.anc[r[1]] | self.anc[r[2]]).bit_count())[:3]:
                source = self.anc[make[1]] | self.anc[make[2]]
                usable = []
                for v, (_, rule) in consumers:
                    if not self.bit[v] & source:
                        other = rule[1] if rule[2] == h else rule[2]
                        drop = self.private[v] & ~(source | self.anc[other])
                        usable.append((drop.bit_count(), v, rule))
                usable.sort(reverse=True)
                # Multi-output patches can share an old tail too. Keep the best group
                # and pairs; actual gain is computed later on the complete rooted graph.
                candidates = [usable[:8], *combinations(usable[:5],2)] if len(usable)>=2 else []
                seen = set()
                for group in candidates:
                    key = tuple(v for _,v,_ in group)
                    if key in seen or self.served_count(key)<2:
                        continue
                    seen.add(key)
                    score = sum(gain for gain,_,_ in group)-1
                    if score>=0:
                        patch = (make, *(r for _,_,r in group))
                        proposals.append((score,rng.random(),patch))
        return sorted(proposals,reverse=True)

    def missing_rewrites(self, rng):
        # Fix any one costly internal output v. Invert its final operation against
        # each existing operand, then join the missing h to an actual one-step recipe.
        # Postdominated ancestors give the exact saving for a single substitution.
        needs = defaultdict(list)
        endpoints = sorted(self.graph,key=lambda v:(-self.private[v].bit_count(), v))[:90]
        for v in endpoints:
            private = self.private[v]
            if private.bit_count() < 2:
                break
            for a in self.values:
                if self.anc[a] & self.bit[v]:
                    continue
                droppable = private & ~self.anc[a]
                if droppable.bit_count() < 2:
                    continue
                for op, x, y in inverse(v, a, self.limit):
                    h = y if x == a else x
                    if 0 < h <= self.limit and h not in self.anc:
                        needs[h].append((v, droppable, (op, x, y, v)))
        if not needs:
            return []
        best = {}
        for a, b in combinations_with_replacement(self.values, 2):
            source = self.anc[a] | self.anc[b]
            for make in rules(a,b,self.limit):
                for v, droppable, last in needs.get(make[3], ()):
                    if source & self.bit[v]:
                        continue
                    gain = (droppable & ~source).bit_count() - 1
                    if gain > 0:
                        proposal = (gain, rng.random(), (make,last))
                        if v not in best or best[v][:2] < proposal[:2]:
                            best[v] = proposal
        return sorted(best.values(),reverse=True)

    def served_count(self, values):
        mask = 0
        for v in values:
            mask |= self.serves[v]
        return mask.bit_count()


def improve(puzzle, program, seed=20261126, rounds=8, *, missing_only=False):
    rng = random.Random(seed)
    starts = set(json.loads(puzzle['starting_values']))
    goals = json.loads(puzzle['targets'])
    limit = int(puzzle['value_limit'])
    best = program
    original = program_rules(puzzle, program)
    graph = {}
    for rule in original:
        if rule[3] not in starts:
            graph.setdefault(rule[3],rule)
    rank = {v:i for i,v in enumerate(graph)}
    seq = schedule(starts, goals, graph, rank)
    stats = dict(curve=[len(best)], witnesses=[], counts=Counter())
    if seq is None:
        return best, stats
    if len(seq)<len(best):
        trial = compile_changes(puzzle,seq,goals)
        if trial is not None:
            best = trial
            stats['curve'].append(len(best))
    if not seq:
        return best,stats

    def test(patch, mode, context):
        changes = {r[3]:r for r in patch}
        candidate_graph = context.graph | changes
        order = schedule(starts,goals,candidate_graph,context.rank)
        if order is None or len(order)>=len(best):
            return None
        if mode=='new_shared_helper':
            h = patch[0][3]
            if sum(h in r[1:3] for r in order)<2:
                return None
        trial = compile_changes(puzzle,order,goals)
        if trial is None:
            order = rooted_rules(starts,goals,candidate_graph)
            trial = compile_changes(puzzle,order,goals)
        return (order,trial) if trial is not None and len(trial)<len(best) else None

    def accept(patch, mode, context, result):
        nonlocal seq, best
        seq, trial = result
        current = {r[3] for r in seq}
        stats['witnesses'].append(dict(kind=mode, before=len(best),after=len(trial),
            rules=patch,removed=sorted(context.graph.keys()-current),
            old_rules=[context.graph[r[3]] for r in patch if r[3] in context.graph]))
        best = trial
        stats['curve'].append(len(best))

    for _ in range(rounds):
        before = len(best)
        context = Context(starts,goals,seq,limit)
        if missing_only:
            proposals = context.missing_rewrites(rng)
            stats['counts']['missing_profitable_endpoints'] += len(proposals)
            for _, _, patch in proposals[:24]:
                make, last = patch
                h = make[3]
                if last[3] not in context.graph or any(v not in context.anc for v in make[1:3]):
                    continue
                if any(v != h and v not in context.anc for v in last[1:3]):
                    continue
                # An earlier accepted patch can already have generated this helper.
                patch = (last,) if h in context.anc else patch
                result = test(patch,'missing_operand',context)
                if result is not None:
                    accept(patch,'missing_operand',context,result)
                    context = Context(starts,goals,seq,limit)
            if before == len(best):
                break
            continue
        proposals = context.single_rewrites(rng)
        stats['counts']['direct_profitable']+=len(proposals)
        # Evaluate several changes against the updated graph. Stale proposals that
        # now use an unavailable value or cease to shorten the DAG cannot enter it.
        for _, _, rule in proposals[:48]:
            if rule[3] not in context.graph or any(v not in context.anc for v in rule[1:3]):
                continue
            result = test([rule], 'existing_values', context)
            if result is not None:
                accept([rule], 'existing_values', context, result)
                context = Context(starts,goals,seq,limit)
        proposals = context.shared_rewrites(rng)
        stats['counts']['shared_ranked']+=len(proposals)
        choice = None
        for _, _, patch in proposals[:100]:
            result = test(patch,'new_shared_helper',context)
            if result is not None and (choice is None or len(result[1])<len(choice[1][1])):
                choice = patch,result
        if choice is not None:
            accept(choice[0],'new_shared_helper',context,choice[1])
        if before==len(best):
            break
    validate(puzzle,best)
    stats['counts']=dict(stats['counts'])
    return best,stats


def improve_missing_operand(puzzle, program, seed=20261126, rounds=4):
    """Additional pass: pay for one missing operand to replace a costly internal branch."""
    return improve(puzzle, program, seed=seed, rounds=rounds, missing_only=True)
