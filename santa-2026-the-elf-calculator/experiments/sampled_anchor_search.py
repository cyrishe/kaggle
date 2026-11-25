"""Compare fixed and sampled outer operands with the same per-target cap."""
import json
import random
import subprocess
import tempfile
from itertools import combinations
from pathlib import Path

from first_solver import validate
from sparse_depth_study import (
    ROOT, DEFAULT_PUZZLES, compile_graph, connect, dependencies, improve_links,
    limited_layers, read_case, run_queries,
)


def trial(binary, puzzle, targets, book, order, cap, edges, differences):
    limit = int(puzzle['value_limit'])
    hits, work = run_queries(binary, limit, order, [(t, True) for t in targets], cap)
    recipes = dict(book)
    for path in hits.values():
        for op, a, b, value in path:
            if op != '=':
                recipes.setdefault(value, (op, a, b, value))
    reached = connect(hits, edges, differences, recipes)
    result = dict(hits=len(hits), reached=len(reached), checks=work['operand_checks'])
    if len(reached) == len(targets):
        program = compile_graph(puzzle, recipes, targets)
        program = improve_links(puzzle, recipes, targets, edges, differences, program)
        validate(puzzle, program)
        result.update(steps=len(program), program=program)
    return result


if __name__ == '__main__':
    puzzle = read_case(DEFAULT_PUZZLES, 'scored_0253')
    targets = sorted(json.loads(puzzle['targets']))
    limit = int(puzzle['value_limit'])
    book, _, _ = limited_layers(json.loads(puzzle['starting_values']), limit)
    supports = dependencies(book)
    keys = sorted(book, key=lambda x: (len(supports[x]), x))
    cap, keep = 128, 32
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / 'query'
        src = Path(__file__).with_name('sparse_depth_query.cpp')
        subprocess.run(['c++', '-O3', '-std=c++17', str(src), '-o', str(binary)], check=True)
        pairs = list(combinations(targets, 2))
        differences, _ = run_queries(binary, limit, keys, [(d, False) for d in sorted({b-a for a,b in pairs})], 0)
        edges = [(a,b) for a,b in pairs if b-a in differences]
        result = dict(id=puzzle['id'], cap=cap, kept=keep, pool=len(keys), seeds={},
                      local_pool_cap=512, local_seeds={})
        result['fixed'] = trial(binary, puzzle, targets, book, keys, cap, edges, differences)
        for name, pool in [('seeds', keys[keep:]), ('local_seeds', keys[keep:512])]:
            for seed in range(10):
                sample = random.Random(seed).sample(pool, cap-keep)
                chosen = set(keys[:keep] + sample)
                order = keys[:keep] + sample + [k for k in keys if k not in chosen]
                result[name][seed] = trial(binary, puzzle, targets, book, order, cap, edges, differences)
    (ROOT/'reports/sampled_anchor_search.json').write_text(json.dumps(result, indent=2)+'\n')
    for name in ('seeds', 'local_seeds'):
        for seed, row in result[name].items():
            print(name, seed, {k:v for k,v in row.items() if k != 'program'})
