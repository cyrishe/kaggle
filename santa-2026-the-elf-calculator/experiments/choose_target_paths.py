"""Select alternate independent derivations jointly, then switch internal derivations."""
import json
import random
from collections import Counter, defaultdict
from itertools import combinations, product
from math import prod

from first_solver import validate
from hybrid_graph_search import compile_changes, program_rules, rooted_rules


def slice_path(path, goal, ready):
    """Keep only producers needed by goal, stopping at values already available."""
    if goal in ready:
        return ()
    pending = {goal}
    keep = []
    for row in reversed(path):
        op, a, b, v = row
        if v not in pending:
            continue
        pending.remove(v)
        pending.update(x for x in (a, b) if x not in ready)
        keep.append(row)
    if pending:
        raise ValueError(f"incomplete independent path to {goal}")
    return tuple(reversed(keep))


def optimize_selection(masks, choices, rng):
    """Minimize distinct results in a set of independent paths, including pair moves."""
    n = len(choices)
    indices = list(range(n))
    for _ in range(8):
        rng.shuffle(indices)
        changed = False
        for i in indices:
            others = 0
            for j in indices:
                if j != i:
                    others |= masks[j][choices[j]]
            old = (masks[i][choices[i]] & ~others).bit_count()
            best = min(range(len(masks[i])), key=lambda k: (masks[i][k] & ~others).bit_count())
            if (masks[i][best] & ~others).bit_count() < old:
                choices[i] = best
                changed = True
        if changed:
            continue
        # A pair can switch to a new common helper even if neither switch pays alone.
        saving = 0
        move = None
        for i, j in combinations(indices, 2):
            others = 0
            for k in indices:
                if k not in (i, j):
                    others |= masks[k][choices[k]]
            old = ((masks[i][choices[i]] | masks[j][choices[j]]) & ~others).bit_count()
            for a, mi in enumerate(masks[i]):
                for b, mj in enumerate(masks[j]):
                    diff = old - ((mi | mj) & ~others).bit_count()
                    if diff > saving:
                        saving, move = diff, (i, j, a, b)
        if move is None:
            break
        i, j, a, b = move
        choices[i], choices[j] = a, b
    return tuple(choices)


def compile_graph(puzzle, starts, goals, graph):
    """Try different execution orders of the same paid DAG when the first cannot fit."""
    for order in (goals, list(reversed(goals)), sorted(goals)):
        try:
            seq = rooted_rules(starts, order, graph)
        except (ValueError, KeyError):
            return None
        program = compile_changes(puzzle, seq, goals)
        if program is not None:
            return program
    return None


def private_dependencies(value, graph, uses):
    """Delete the old producer; reclaim ancestors that have no other user or goal."""
    removed = {value}
    pending = [value]
    lost_uses = Counter()
    while pending:
        row = graph[pending.pop()]
        for parent in set(row[1:3]):
            if parent not in graph:
                continue
            lost_uses[parent] += 1
            if lost_uses[parent] == uses[parent]:
                removed.add(parent)
                pending.append(parent)
    return removed


def local_exchange(puzzle, starts, goals, options, baseline, stats):
    """Replace whole internal subderivations only with recipes witnessed in solo paths."""
    best = baseline
    for _ in range(16):
        original = program_rules(puzzle, best)
        graph = {r[-1]: r for r in original if r[-1] not in starts}
        if len(graph) != len(original):
            break
        descendants = {v: set() for v in graph}
        uses = Counter(goals)
        for row in reversed(original):
            v = row[-1]
            for parent in set(row[1:3]) & graph.keys():
                descendants[parent].add(v)
                descendants[parent].update(descendants[v])
                uses[parent] += 1
        proposals = []
        for value, paths in options.items():
            if value not in graph or len(paths) < 2:
                continue
            removed = private_dependencies(value, graph, uses)
            if len(removed) <= 1:
                continue
            ready = starts | (graph.keys() - removed - descendants[value])
            for path in paths:
                patch = slice_path(path, value, ready)
                saving = len(removed) - len(patch)
                if saving <= 0 or any(r[-1] in descendants[value] for r in patch):
                    continue
                proposals.append((saving, value, patch))
        accepted = False
        for saving, value, patch in sorted(proposals, key=lambda item: -item[0])[:48]:
            candidate = graph.copy()
            candidate.update((r[-1], r) for r in patch)
            program = compile_graph(puzzle, starts, goals, candidate)
            if program is not None and len(program) < len(best):
                stats["internal_swaps"].append(dict(value=value, steps_before=len(best),
                    steps_after=len(program), new_last_rule=patch[-1]))
                best = program
                accepted = True
                break
        if not accepted:
            break
    return best


def choose(puzzle, catalog, incumbent, seed=20261126):
    """Return the shortest replayable program found and the stage-by-stage counts."""
    rng = random.Random(seed)
    starts = set(json.loads(puzzle['starting_values']))
    goals = list(dict.fromkeys(json.loads(puzzle['targets'])))
    validate(puzzle, incumbent)
    paths = []
    options = defaultdict(dict)
    for goal in goals:
        if goal in starts:
            paths.append([()])
            continue
        alternatives = {}
        for path in catalog[goal]:
            clean = slice_path([tuple(row) for row in path], goal, starts)
            alternatives.setdefault(clean, None)
            for position, row in enumerate(clean):
                value = row[-1]
                subpath = slice_path(clean[:position+1], value, starts)
                options[value].setdefault(subpath, None)
        if not alternatives:
            raise ValueError(f"missing solo paths for target {goal}")
        paths.append(sorted(alternatives, key=len))
    values = {r[-1] for ps in paths for p in ps for r in p}
    bit = {v: 1 << i for i, v in enumerate(sorted(values))}
    masks = [[sum(bit[v] for v in {r[-1] for r in p}) for p in ps] for ps in paths]
    n = len(goals)
    selections = {tuple([0] * n)}
    combinations_count = prod(map(len, masks))
    if combinations_count <= 512:
        selections.update(product(*(range(len(ms)) for ms in masks)))
    else:
        for trial in range(8):
            start = [0 if not trial else rng.randrange(len(ms)) for ms in masks]
            selections.add(optimize_selection(masks, start, rng))

    def union_size(selection):
        merged = 0
        for i, k in enumerate(selection):
            merged |= masks[i][k]
        return merged.bit_count()

    stats = dict(input_steps=len(incumbent), selections=len(selections), compilations=0,
                 union_steps_before=union_size([0]*n), internal_swaps=[])
    best = incumbent
    indices = list(range(n))
    # Different orderings may take different producers for a shared value.
    for selection in sorted(selections, key=lambda s: (union_size(s), s))[:20]:
        orders = [indices, list(reversed(indices))]
        for _ in range(2):
            order = indices.copy()
            rng.shuffle(order)
            orders.append(order)
        for order in orders:
            # Concatenation respects dependencies even when two paths use different
            # recipes for the same number. The earliest producer wins.
            graph = {}
            for i in order:
                for r in paths[i][selection[i]]:
                    graph.setdefault(r[-1], r)
            wanted = [goals[i] for i in order]
            stats["compilations"] += 1
            program = compile_graph(puzzle, starts, wanted, graph)
            if program is not None and len(program) < len(best):
                stats['selected_indices'] = list(selection)
                best = program
    stats['after_whole_paths'] = len(best)
    best = local_exchange(puzzle, starts, goals, options, best, stats)
    stats['after_internal_sources'] = len(best)
    validate(puzzle, best)
    return best, stats
