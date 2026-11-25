"""Measure instruction DAG depths and join a shallow forward dictionary to target equations."""
import argparse
import csv
import json
import mmap
import subprocess
import sys
import tempfile
from itertools import combinations, combinations_with_replacement, product
from pathlib import Path
from statistics import median

from export_50_baseline_cases import DEFAULT_PUZZLES, ROOT, replay
from first_solver import validate
from probe_baseline_pair import compile_values


def dag(puzzle, program):
    starts = json.loads(puzzle['starting_values'])
    version = dict(enumerate(range(-len(starts), 0)))
    nodes = {v: dict(step=v, value=s, depth=0, register=r) for r,(v,s) in enumerate(zip(version.values(),starts))}
    targets = set(json.loads(puzzle['targets']))
    for n,i,a,op,j,b,d,v,hit in replay(puzzle,program):
        left,right=version[i],version[j]
        nodes[n]=dict(step=n, value=v, operands=[left,right], op=op, register=d,
                      depth=1+max(nodes[left]['depth'],nodes[right]['depth']), target=v in targets, first=bool(hit and '首次' in hit))
        version[d]=n
    return list(nodes.values())


def rules(a,b,limit):
    yield '+',a,b,a+b
    yield '-',b,a,b-a
    if a*b<=limit:
        yield '*',a,b,a*b
    if b%a==0:
        yield '/',b,a,b//a


def shallow(starts,limit,depth):
    book=dict.fromkeys(starts)
    totals=[len(book)]
    for _ in range(depth):
        for a,b in combinations_with_replacement(sorted(book),2):
            for op,x,y,v in rules(a,b,limit):
                if 0<v<=limit:
                    book.setdefault(v,(op,x,y,v))
        totals.append(len(book))
    return book,totals


def inverse(t, a, limit):
    yield '+',a,t-a
    yield '-',a,a-t
    yield '-',t+a,a
    if t%a==0:
        yield '*',a,t//a
    if a%t==0:
        yield '/',a,a//t
    if t*a<=limit:
        yield '/',t*a,a


def expand0253(puzzle,tmp):
    starts=json.loads(puzzle['starting_values'])
    goals=json.loads(puzzle['targets'])
    limit=int(puzzle['value_limit'])
    book,counts=shallow(starts,limit,2)
    keys=sorted(book)
    f1,_=shallow(starts,limit,1)
    binary=tmp/'expand'
    bits_path=tmp/'bits'
    subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('dense_depth_layer.cpp')),'-o',str(binary)],check=True)
    data=f'{limit} {len(keys)}\n'+' '.join(map(str,keys))
    counts.append(int(subprocess.check_output([str(binary),str(bits_path)],input=data,text=True)))
    if sys.byteorder!='little':
        raise RuntimeError('Expected a little-endian bitmap')
    with bits_path.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as bits:
        def marked(x):
            return 0<x<=limit and bool(bits[x//8] & (1<<(x%8)))
        def recover(t):
            if t not in book:
                for a in keys:
                    for op,x,y in inverse(t,a,limit):
                        if x in keyset and y in keyset:
                            book[t]=(op,x,y,t)
                            return
                raise ValueError(f'no derivation for {t}')
        keyset=set(keys)
        direct=[t for t in goals if marked(t)]
        links=[(u,v) for u,v in combinations(goals,2) if marked(v-u)]
        available=set(direct)
        while True:
            extra={v for u,v in links if u in available}|{u for u,v in links if v in available}
            if extra<=available:break
            available.update(extra)
        components=[]
        rest=set(goals)
        while rest:
            group={min(rest)}
            while True:
                extra={v for u,v in links if u in group}|{u for u,v in links if v in group}
                if extra<=group:break
                group.update(extra)
            rest-=group
            components.append(sorted(group))
        # Goal-driven join at depth <=4. Try a cheap operand from layer 0..2
        # first; as fallback enumerate exact layer-3 members until a partner exists.
        def witnesses(t):
            for a in sorted(keys,key=lambda x:(x not in starts,x not in f1,x)):
                for op,x,y in inverse(t,a,limit):
                    if marked(x) and marked(y):
                        yield (op,x,y,t)
            for byte_index in range(len(bits)):
                mask=bits[byte_index]
                while mask:
                    bit=mask & -mask
                    a=byte_index*8+bit.bit_length()-1
                    for op,x,y in inverse(t,a,limit):
                        if marked(x) and marked(y):
                            yield (op,x,y,t)
                    mask-=bit
        for t in goals:
            if t in direct:
                recover(t)
            else:
                op,x,y,v=next(witnesses(t))
                recover(x)
                recover(y)
                book[t]=(op,x,y,v)
        def compile_plan(recipes):
            placed=set(starts)
            active=set()
            plan=[]
            def visit(v):
                if v in placed:return True
                if v in active:return False
                active.add(v)
                rule=recipes[v]
                if not visit(rule[1]) or not visit(rule[2]):return False
                active.remove(v)
                placed.add(v)
                plan.append(rule)
                return True
            return plan if all(visit(t) for t in goals) else None

        def verified(plan):
            program=compile_values(puzzle,plan,goals)
            nodes=dag(puzzle,program)
            return dict(steps=len(program),max_depth=max(n['depth'] for n in nodes),
                        coverage=validate(puzzle,program)[2],
                        registers_used=len({i for op in program for i in op[1:]}),program=program)

        best_plan=compile_plan(book)
        direct_result=verified(best_plan)
        chosen=[]
        for u,v in links:
            recover(v-u)
        for orientations in product((0,1,-1),repeat=len(links)):
            changes={}
            for (u,v),direction in zip(links,orientations):
                if direction==0:continue
                rule=('+',u,v-u,v) if direction==1 else ('-',v,v-u,u)
                if rule[3] in changes:break
                changes[rule[3]]=rule
            else:
                plan=compile_plan(book|changes)
                if plan is not None and len(plan)<len(best_plan):
                    try:
                        verified(plan)
                    except ValueError as e:
                        if str(e)!='register budget exceeded':raise
                        continue
                    best_plan=plan
                    chosen=list(changes.values())
        return dict(counts=counts, matched_at_depth3=direct, edges=links,
                    components=components,reached_from_depth3=sorted(available),
                    forward_bits_bytes=len(bits),verified_join=direct_result,
                    conditional_join=verified(best_plan),chosen_conditional_rules=chosen)



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('submission', type=Path)
    parser.add_argument('--out',type=Path,default=ROOT/'reports/depth_graph_study.json')
    args=parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:puzzles={r['id']:r for r in csv.DictReader(f)}
    rows=[]
    cases={}
    with args.submission.open() as f:
        for r in csv.DictReader(f):
            ident=r['id'];program=json.loads(r['program'])
            nodes=dag(puzzles[ident],program)
            rows.append(dict(id=ident,steps=len(program),depth=max(n['depth'] for n in nodes),
                             target_depth=max([n['depth'] for n in nodes if n.get('first')]+[0])))
            cases[ident]=nodes
    assert len(rows)==len(puzzles)==len({r['id'] for r in rows})
    longest=max(rows,key=lambda r:r['steps'])
    deepest=max(rows,key=lambda r:r['depth'])
    report=dict(longest=longest,deepest=deepest,median_depth=median(r['depth'] for r in rows),
                all_cases=rows,graphs={i:cases[i] for i in {longest['id'],deepest['id'],'scored_0253'}})
    p=puzzles[longest['id']]
    book,counts=shallow(json.loads(p['starting_values']),int(p['value_limit']),3)
    report['longest_forward']=dict(counts=counts,exact_goal_hits=sorted(set(json.loads(p['targets'])) & book.keys()))
    with tempfile.TemporaryDirectory() as d:
        report['0253_forward']=expand0253(puzzles['scored_0253'],Path(d))
    args.out.write_text(json.dumps(report,separators=(',',':'))+'\n')
    print(longest,deepest,report['median_depth'],report['longest_forward'])
    print({k:v for k,v in report['0253_forward'].items() if k not in ('verified_join','conditional_join')})
    for variant in ('verified_join','conditional_join'):
        print(variant,{k:v for k,v in report['0253_forward'][variant].items() if k!='program'})


if __name__=='__main__':
    main()
