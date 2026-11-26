"""Extract a small complete arithmetic DAG from the union of independent programs.

Each constructed value is paid for once. A live value needs one selected recipe;
strict ranks within cyclic components forbid recipes that justify each other.
Register use is checked separately by compiling and replaying every saved result.
"""

import argparse
import csv
import gzip
import json
import random
import sys
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations_with_replacement
from pathlib import Path

from converge_target_paths import schedule
from first_solver import validate
from hybrid_graph_search import compile_changes, program_rules, rooted_rules
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
IDS = ["scored_%04d" % i for i in (2, 60, 78, 529, 74, 489)]


def canon(rule):
    op, a, b, v = rule
    return (op, b, a, v) if op in ("+", "*") and b < a else tuple(rule)


def load(name):
    path = REPORTS / name
    if name == "collective_control_donors.json" and not path.exists():
        from hybrid_graph_search import Construction, live_rollout

        with (ROOT / "data/puzzles.csv").open() as stream:
            puzzles = [r for r in csv.DictReader(stream) if r["id"] in IDS]
        cases = {}
        for puzzle in puzzles:
            prog, _ = live_rollout(
                Construction(puzzle), seed=20261127, virtual=True, policy="order"
            )
            if prog is not None:
                validate(puzzle, prog)
                cases[puzzle["id"]] = {"program": prog}
        path.write_text(json.dumps({"cases": cases}, separators=(",", ":")) + "\n")
    with gzip.open(path, "rt") if name.endswith(".gz") else path.open() as f:
        return json.load(f)


def fetch_donors(extra):
    pool = load("collective_prior_donors.json")["cases"]
    for name in ("collective_control_donors.json", *extra):
        data = load(name)
        cases = data.get("cases", data)
        for ident in IDS:
            if ident not in cases:
                continue

            def collect(record, key):
                if not isinstance(record, dict):
                    return
                if isinstance(record.get("program"), list) and record["program"]:
                    pool[ident][key] = record["program"]
                if record.get("best_program"):
                    pool[ident][key + "/best"] = record["best_program"]
                for j, prog in enumerate(
                    record.get("programs", []) + record.get("alternatives", [])
                ):
                    if isinstance(prog, list) and prog and isinstance(prog[0], list):
                        pool[ident][key + "/trial" + str(j)] = prog
                for k, v in record.items():
                    if isinstance(v, dict):
                        collect(v, key + "/" + k)

            collect(cases[ident], name)
    return pool


def components(choices, starts):
    """Tarjan components on dependencies. Only a cyclic component needs ranks."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 3 * len(choices) + 100))
    dependencies = {
        v: {x for r in rr for x in r[1:3]} - starts for v, rr in choices.items()
    }
    index, low, group = {}, {}, {}
    stack, onstack = [], set()

    def visit(v):
        index[v] = low[v] = len(index)
        stack.append(v)
        onstack.add(v)
        for w in sorted(dependencies[v]):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                onstack.remove(w)
                group[w] = v
                if w == v:
                    break

    for v in choices:
        if v not in index:
            visit(v)
    return group


def discover(choices, starts, goals, price, cap):
    """Add genuine one-op connections between values from different donor paths."""
    vals = sorted(choices.keys() | starts)
    extra = defaultdict(set)

    def offer(r):
        v = r[3]
        if v in choices and v not in r[1:3] and r not in choices[v]:
            extra[v].add(r)

    for a, b in combinations_with_replacement(vals, 2):
        s = a + b
        if s in price:
            offer(("+", a, b, s))
            offer(("-", s, a, b))
            offer(("-", s, b, a))
        m = a * b
        if m in price:
            offer(("*", a, b, m))
            offer(("/", m, a, b))
            offer(("/", m, b, a))
    for v, rules in extra.items():
        # Limit the dense low-value region, which otherwise dominates solving time.
        ordered = sorted(
            rules,
            key=lambda r: (max(price[r[1]], price[r[2]]), price[r[1]] + price[r[2]], r),
        )
        choices[v].update(ordered[:cap])
    return sum(min(cap, len(rs)) for rs in extra.values())


def rematerialize(p, graph, seq):
    """Replay a topological order, rebuilding an evicted intermediate on demand."""
    initial = json.loads(p["starting_values"])
    registers = {v: i for i, v in enumerate(initial)}
    free = set(range(int(p["registers"]))) - set(registers.values())
    protected = set(initial)
    uses = defaultdict(deque)
    price = dict.fromkeys(initial, 0)
    for i, (_, a, b, v) in enumerate(seq):
        for w in {a, b}:
            uses[w].append(i)
        price[v] = 1 + min(24, price[a] + (price[b] if b != a else 0))
    out = []

    def make(v, pinned, i):
        if v in registers:
            return
        op, a, b, _ = graph[v]
        make(a, pinned, i)
        make(b, pinned | {a}, i)
        ra, rb = registers[a], registers[b]
        if free:
            dest = free.pop()
        else:
            victims = registers.keys() - pinned - protected
            if not victims:
                raise ValueError("no spill slot")

            def keep(w):
                if not uses[w]:
                    return (0, 0, w)
                delay = max(1, uses[w][0] - i)
                return (1, price[w] / delay, w)

            victim = min(victims, key=keep)
            dest = registers.pop(victim)
        registers[v] = dest
        out.append([op, ra, rb, dest])

    for i, (_, a, b, v) in enumerate(seq):
        for w in {a, b}:
            uses[w].popleft()
        make(v, set(), i)
    validate(p, out)
    return out


def compile_graph(p, starts, goals, graph, donors):
    trials = []
    for seq in donors[:4]:
        order = schedule(starts, goals, graph, {r[3]: i for i, r in enumerate(seq)})
        if order is None:
            return None
        prog = compile_changes(p, order, goals)
        if prog is not None:
            return prog
        goal_order = list(dict.fromkeys(r[3] for r in seq if r[3] in goals))
        trials.append(goal_order)
    rng = random.Random(432)
    for _ in range(10):
        shuffled = list(goals)
        rng.shuffle(shuffled)
        trials.append(shuffled)
    for order in trials:
        seq = rooted_rules(starts, order, graph)
        prog = compile_changes(p, seq, goals)
        if prog is not None:
            return prog
    spill = []
    for order in trials[:4]:
        seq = rooted_rules(starts, order, graph)
        try:
            spill.append(rematerialize(p, graph, seq))
        except ValueError:
            continue
    return min(spill, key=len, default=None)


def extract(job):
    p, bank, time_limit, extra_arcs, max_parents = job
    ident = p["id"]
    starts, goals = set(json.loads(p["starting_values"])), json.loads(p["targets"])
    programs = sorted(bank.values(), key=len)
    seqs, unique = [], set()
    for prog in programs:
        validate(p, prog)
        seq = [canon(r) for r in program_rules(p, prog)]
        sig = frozenset(seq)
        if sig not in unique:
            seqs.append(seq)
            unique.add(sig)
    if len(seqs) > max_parents:
        keep = [seqs[0]]
        others = seqs[1:]
        known = set(seqs[0])
        while others and len(keep) < max_parents:
            # Small and structurally different donors give alternatives inside the time cap.
            winner = min(others, key=lambda s: len(s) - 0.18 * len(set(s) - known))
            others.remove(winner)
            keep.append(winner)
            known.update(winner)
        seqs = keep
    choices = defaultdict(set)
    price = dict.fromkeys(starts, 0)
    for seq in seqs:
        local = dict.fromkeys(starts, 0)
        for r in seq:
            op, a, b, v = r
            if v in starts or v in (a, b):
                continue
            choices[v].add(r)
            score = 1 + max(local[a], local[b])
            local[v] = min(score, local.get(v, score))
            price[v] = min(score, price.get(v, score))
    raw_recipes = sum(map(len, choices.values()))
    extra_count = (
        discover(choices, starts, goals, price, extra_arcs) if extra_arcs else 0
    )
    incumbent = programs[0]
    seedgraph = {}
    for r in seqs[0]:
        if r[3] not in starts:
            seedgraph.setdefault(r[3], r)
    seed_seq = rooted_rules(starts, goals, seedgraph)
    seed = {r[3]: r for r in seed_seq}
    normalized = compile_graph(p, starts, goals, seed, seqs)
    if normalized is not None and len(normalized) < len(incumbent):
        incumbent = normalized
    group = components(choices, starts)
    model = cp_model.CpModel()
    live = {v: model.NewBoolVar("") for v in choices}
    rank, picks = {}, {}
    for g in goals:
        if g not in starts:
            model.Add(live[g] == 1)
    for v, rr in choices.items():
        options = []
        for r in sorted(rr):
            pick = live[v] if len(rr) == 1 else model.NewBoolVar("")
            options.append(pick)
            picks[r] = pick
            for x in set(r[1:3]) - starts:
                model.AddImplication(pick, live[x])
                if group[x] == group[v]:
                    for n in (x, v):
                        if n not in rank:
                            rank[n] = model.NewIntVar(0, len(live), "")
                    model.Add(rank[x] < rank[v]).OnlyEnforceIf(pick)
        if len(rr) > 1:
            model.Add(sum(options) == live[v])
    for v, var in live.items():
        model.AddHint(var, int(v in seed))
        if len(choices[v]) > 1:
            for r in choices[v]:
                model.AddHint(picks[r], int(seed.get(v) == r))
    order = {r[3]: i + 1 for i, r in enumerate(seed_seq)}
    for v, var in rank.items():
        model.AddHint(var, order.get(v, 0))
    model.Add(sum(live.values()) <= len(seed))
    model.Minimize(sum(live.values()))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.random_seed = 123
    # The complete incumbent hint lets the solver start at a valid graph.
    solver.parameters.cp_model_presolve = True
    status = solver.Solve(model)
    obj = None
    accepted = False
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        graph = {r[3]: r for r, var in picks.items() if solver.Value(var)}
        obj = round(solver.ObjectiveValue())
        prog = compile_graph(p, starts, goals, graph, seqs)
        if prog is not None and len(prog) < len(incumbent):
            incumbent, accepted = prog, True
    result = dict(
        before=len(programs[0]),
        normalized=len(normalized) if normalized is not None else None,
        steps=validate(p, incumbent)[0],
        program=incumbent,
        donors={k: len(v) for k, v in bank.items()},
        unique_parents=len(seqs),
        values=len(live),
        donor_recipes=raw_recipes,
        extra_recipes=extra_count,
        status=solver.StatusName(status),
        objective=obj,
        accepted=accepted,
        search_seconds=round(solver.WallTime(), 3),
    )
    print(ident, result["before"], result["steps"], result["status"], obj, flush=True)
    return ident, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--donors",
        action="append",
        default=[],
        help="independently generated report inside reports/",
    )
    parser.add_argument("--ids", nargs="+", choices=IDS, default=IDS)
    parser.add_argument("--parents", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=6)
    parser.add_argument("--extra-arcs", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pool = fetch_donors(args.donors)
    with (ROOT / "data/puzzles.csv").open() as f:
        puzzles = {p["id"]: p for p in csv.DictReader(f)}
    jobs = [
        (puzzles[i], pool[i], args.seconds, args.extra_arcs, args.parents)
        for i in args.ids
    ]
    with ProcessPoolExecutor(args.workers) as workers:
        cases = dict(workers.map(extract, jobs))
    args.output.write_text(
        json.dumps(
            dict(
                parents=args.parents,
                extra_arcs=args.extra_arcs,
                seconds=args.seconds,
                cases=cases,
            ),
            separators=(",", ":"),
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
