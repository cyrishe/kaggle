"""Bounded single-output arithmetic search. Each query sees only starts and one target."""
import json
from bisect import bisect_left
from functools import lru_cache
from itertools import combinations_with_replacement

from depth_graph_study import rules
from hybrid_graph_search import compile_changes, rooted_rules


def closure(starts, limit):
    """Index short starting-value computations by output and instruction count.

    The last instruction either combines independent subtrees, or one side is
    already present in the other side's (at most two-instruction) computation.
    Store one representative per value, so the latter case is only sampled.
    """
    plans = {value: () for value in starts}
    levels = [sorted(plans)]
    for size in (1, 2, 3):
        found = []
        def add(a, b):
            prefix = plans[a] + tuple(rule for rule in plans[b] if rule not in plans[a])
            if len(prefix) >= size:
                return
            for op, x, y, v in rules(*sorted((a, b)), limit):
                if 0 < v <= limit and v not in plans:
                    plans[v] = prefix + ((op, x, y, v),)
                    found.append(v)
        for left in range((size - 1) // 2 + 1):
            right = size - 1 - left
            if left == right:
                for a, b in combinations_with_replacement(levels[left], 2):
                    add(a, b)
            else:
                for a in levels[left]:
                    for b in levels[right]:
                        add(a, b)
        if size > 1:
            for a in levels[-1]:
                for row in plans[a]:
                    add(a, row[-1])
        levels.append(found)
    return plans, levels


class IsolatedSolver:
    def __init__(self, starts, limit, registers):
        self.starts = tuple(starts)
        self.limit = int(limit)
        self.registers = int(registers)
        self.plans, layers = closure(self.starts, self.limit)
        self.ordered = sorted(self.plans)
        self.cheap_offsets = set(self.starts) | set(layers[1])
        # Include values at each magnitude without letting a large dense layer
        # displace the actual starts or cheap powers and multiples.
        pivots = set(self.starts) | set(layers[1])
        by_bits = {}
        for value in layers[2] + layers[3]:
            by_bits.setdefault(value.bit_length(), []).append(value)
        for values in by_bits.values():
            pivots.update(values[:3])
        pivots.update(v for v in (2, 3, 4, 5, 8, 10, 16, 32, 64, 128, 256) if v in self.plans)
        self.pivots = sorted(pivots - {1})
        self.meet = list(dict.fromkeys([*self.starts, *self.pivots, *layers[2], *layers[3]]))
        self.operands = {v: frozenset(row[-1] for row in path) for v,path in self.plans.items()}

    def paths(self, target):
        if not 1 <= target <= self.limit:
            raise ValueError('target outside positive calculator range')
        if target in self.starts:
            return [[]]
        plans, limit = self.plans, self.limit
        puzzle = dict(starting_values=json.dumps(self.starts), targets=json.dumps([target]),
                      value_limit=limit, registers=self.registers)
        answers = {}
        fingerprints = set()
        def offer(raw):
            # Different pieces can incidentally compute one another's results.
            # Keeping the first producer gives a topological graph.
            graph = {}
            for rule in raw:
                if rule[3] != rule[1] and rule[3] != rule[2]:
                    graph.setdefault(rule[3], rule)
            seq = tuple(rooted_rules(self.starts, [target], graph))
            if len(seq) > min((len(path) for path in answers), default=4096) + 3:
                return
            signature = frozenset((op,min(a,b),max(a,b),v) if op in ("+", "*") else (op,a,b,v)
                                  for op,a,b,v in seq)
            if signature not in fingerprints and compile_changes(puzzle, seq, [target]) is not None:
                fingerprints.add(signature)
                answers[seq] = len(seq)
                if len(answers) > 36:
                    longest = max(answers, key=answers.get)
                    del answers[longest]

        # Always have an isolated construction, including targets too large to
        # reach by the forward table. Building the radix/digits themselves costs steps.
        bases = sorted({2, 3, 4, 8, 16, 32} | {v for v in self.starts if 2 <= v <= 64})
        @lru_cache(maxsize=128)
        def radix(value, base):
            rows = []
            made = set(self.starts)
            def make(value):
                if value in made:
                    return
                if value in plans:
                    for rule in plans[value]:
                        if rule[-1] not in made:
                            rows.append(rule)
                            made.add(rule[-1])
                    return
                if value <= base:
                    child = value // 2 if value % 2 == 0 else value - 1
                    other = child if value % 2 == 0 else 1
                    make(child)
                    make(other)
                    rule = ('+', child, other, value)
                else:
                    q, r = divmod(value, base)
                    if r:
                        make(value - r)
                        make(r)
                        rule = ('+', value - r, r, value)
                    else:
                        make(q)
                        make(base)
                        rule = ('*', q, base, value)
                rows.append(rule)
                made.add(value)
            make(value)
            return rows
        for base in bases:
            if base <= limit:
                offer(radix(target, base))
        if target in plans:
            offer(plans[target])
        if target == 1 and target in plans and limit == 1:
            return [list(plans[target])]

        # Work backwards as n = q*b +/- r. Freeze b and r, then keep several
        # inexpensive quotients unresolved. Charging their constructor union
        # rewards reusing the same base or offset within the individual program.
        def wrap(path, suffix):
            out = list(path)
            for base, q, rem, n in reversed(suffix):
                out.extend(plans[base])
                product = q * base
                out.append(('*', q, base, product))
                if rem:
                    out.extend(plans[abs(rem)])
                    out.append(('+' if rem > 0 else '-', product, abs(rem), n))
            return out

        @lru_cache(maxsize=None)
        def finishes(n, broad):
            matches = []
            if n in plans:
                matches.append((len(plans[n]), plans[n]))
            def match(a, b, op):
                if b in plans and n not in (a, b):
                    final = (op, a, b, n)
                    if op == 'r-':
                        final = ('-', b, a, n)
                    elif op == 'r/':
                        final = ('/', b, a, n)
                    score = 1 + len(self.operands[a] | self.operands[b])
                    if len(matches) < 6 or score <= worst[0]:
                        matches.append((score, plans[a] + plans[b] + (final,)))
                        if len(matches) >= 12:
                            matches.sort(key=lambda x:x[0])
                            del matches[6:]
                        if len(matches) >= 6:
                            worst[0] = max(s for s,_ in matches)
            worst = [10]
            for a in self.meet[:(4096 if broad else 64)]:
                match(a, n-a, '+')
                match(a, a-n, '-')
                match(a, n+a, 'r-')
                if n % a == 0:
                    match(a,n//a,'*')
                if a % n == 0:
                    match(a,a//n,'/')
                if n <= limit // a:
                    match(a,n*a,'r/')
            return [path for _,path in sorted(matches,key=lambda x:x[0])[:5]]

        states = [(target, (), frozenset(), 0)]
        for depth in range(9):
            nxt = {}
            for index, (n, suffix, paid, overhead) in enumerate(states):
                for plan in finishes(n, depth == 0):
                    offer(wrap(plan, suffix))
                if depth and index < 3:
                    for base in bases:
                        if base <= limit:
                            offer(wrap(radix(n, base), suffix))
                if depth == 8:
                    continue
                options = []
                # Large exact factors lying outside the ordinary pivot menu
                # can make a hard quotient much smaller in a single instruction.
                extra = []
                if depth == 0:
                    for a in self.meet:
                        if 1 < a < n:
                            rem = n % a
                            if rem == 0 or min(rem, a-rem) in self.cheap_offsets:
                                extra.append(a)
                elif depth == 1:
                    extra = [a for a in self.meet if a > 1 and n % a == 0]
                for base in sorted(set(self.pivots) | set(extra)):
                    if base >= n:
                        break
                    q, rem = divmod(n, base)
                    choices = [(q, rem)]
                    if rem and n + base - rem <= limit:
                        choices.append((q + 1, rem - base))
                    if depth == 0:
                        pos = bisect_left(self.ordered,q)
                        for near in self.ordered[max(0,pos-2):pos+3]:
                            delta = n - near * base
                            if near < n and near * base <= limit and delta and abs(delta) in plans:
                                choices.append((near,delta))
                    for quotient, residual in choices:
                        if quotient >= n or (residual and abs(residual) not in plans):
                            continue
                        extra = self.operands[base]
                        if residual:
                            extra = extra | self.operands[abs(residual)]
                        new_paid = paid | extra
                        steps = overhead + 1 + bool(residual)
                        if quotient in plans:
                            estimate = len(new_paid | self.operands[quotient]) + steps
                            options.append((estimate, base, quotient, residual))
                        elif quotient > 1:
                            estimate = len(new_paid) + steps + 1.7 + quotient.bit_length() * 0.34
                        else:
                            continue
                        key = (quotient, base)
                        if key not in nxt or estimate < nxt[key][0]:
                            nxt[key] = (estimate, quotient, suffix+((base,quotient,residual,n),), new_paid, steps)
                for _,base,q,r in sorted(options)[:6]:
                    offer(wrap(plans[q], suffix+((base,q,r,n),)))
            states = []
            counts = {}
            for score, q, suffix, paid, overhead in sorted(nxt.values(), key=lambda s:s[0]):
                if q in plans or counts.get(q,0) >= 2:
                    continue
                states.append((q,suffix,paid,overhead))
                counts[q] = counts.get(q,0)+1
                if len(states) == 8:
                    break
        ranked = sorted(answers, key=lambda s:(len(s),s))
        if not ranked:
            raise ValueError(f'No independently schedulable route for {target}')
        # Keep the shortest, then discriminate between equally short formulas
        # by how many of their intermediates already occur in the selected ones.
        chosen = []
        used = set()
        while ranked and len(chosen) < 4:
            shortest = len(ranked[0])
            contenders = [p for p in ranked if len(p)==shortest]
            best = min(contenders, key=lambda p:sum(v in used for _,_,_,v in p))
            ranked.remove(best)
            chosen.append(list(best))
            used.update(r[-1] for r in best)
        return chosen
