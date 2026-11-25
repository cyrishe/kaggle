"""Control: change only one opcode of a strong, known feasible public program."""
import csv
import json
import random
from collections import Counter
from baseline_lineage import DEFAULT_PUZZLES, ROOT
from benchmark_hybrid_graph import load_reference
from capped_path_walk import CASES, SEED
from first_solver import validate


def inspect(puzzle, program):
    starts = json.loads(puzzle['starting_values'])
    limit = int(puzzle['value_limit'])
    expected = set(json.loads(puzzle['targets']))
    registers = starts + [None]*(int(puzzle['registers'])-len(starts))
    covered = expected.intersection(starts)
    for op,i,j,d in program:
        a,b = registers[i],registers[j]
        if op=='+':
            v = a+b
        elif op=='-':
            v = a-b
        elif op=='*':
            v = a*b
        elif a%b:
            return 'illegal'
        else:
            v = a//b
        if not 0<v<=limit:
            return 'illegal'
        registers[d] = v
        if v in expected:
            covered.add(v)
    if covered!=expected:
        return 'missed_targets'
    validate(puzzle,program)
    return 'full'


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as f:
        puzzles={r['id']:r for r in csv.DictReader(f)}
    rows=[]
    for ident in CASES:
        initial=load_reference(ident)
        validate(puzzles[ident],initial)
        rng=random.Random(SEED+int(ident[-4:]))
        results=Counter()
        for _ in range(200):
            candidate=list(initial)
            idx=rng.randrange(len(candidate))
            op,*regs=candidate[idx]
            candidate[idx]=[rng.choice([s for s in '+-*/' if s!=op])]+regs
            results[inspect(puzzles[ident],candidate)] += 1
        rows.append(dict(id=ident,steps=len(initial),results=results))
    print(rows)
    (ROOT/'reports/public_single_edit_walk.json').write_text(json.dumps(rows,indent=2)+'\n')
