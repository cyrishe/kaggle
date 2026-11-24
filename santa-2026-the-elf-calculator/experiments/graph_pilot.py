#!/usr/bin/env python3
"""Conservative graph rewrite pilot for scored_0810; see graph_pilot.md."""
import argparse, csv, json, hashlib
from pathlib import Path
from first_solver import validate

ROOT = Path(__file__).resolve().parent.parent
STARTS = [4, 7, 10, 13]
LIMIT = 192455053

def evaluate(op, a, b):
    if a is None or b is None: return None
    if op == '+': v = a + b
    elif op == '-': v = a - b
    elif op == '*': v = a * b
    elif op == '/' and b and a % b == 0: v = a // b
    else: return None
    return v if 0 < v <= LIMIT else None

def replay(program):
    regs = STARTS + [None] * (48-len(STARTS)); versions = [None]*48
    nodes, snapshots = [], []
    for i, (op, a, b, d) in enumerate(program):
        snapshots.append(regs[:]); value = evaluate(op, regs[a], regs[b])
        if value is None: raise ValueError(f'illegal operation at {i+1}')
        nodes.append((value, versions[a], versions[b], op, a, b, d))
        regs[d], versions[d] = value, i
    return nodes, snapshots

def prune(program, protected):
    nodes, _ = replay(program); need=set(); found=set(STARTS)&protected
    for i, node in enumerate(nodes):
        if node[0] in protected and node[0] not in found:
            need.add(i); found.add(node[0])
    if found != protected: raise ValueError('missing protected values')
    stack=list(need)
    while stack:
        node=nodes[stack.pop()]
        for dep in node[1:3]:
            if dep is not None and dep not in need: need.add(dep); stack.append(dep)
    return [op for i, op in enumerate(program) if i in need]

def dot(program, protected, path):
    nodes, _ = replay(program)
    out=['digraph calculator {','rankdir=LR;','node [shape=box,fontsize=9];']
    for i,v in enumerate(STARTS): out.append(f's{i} [label="start r{i}: {v}",shape=oval];')
    for i,(v,l,r,op,a,b,d) in enumerate(nodes):
        color='lightgoldenrod1' if v in protected else 'white'
        out.append(f'n{i} [label="{i+1}: {v}\\n{op} r{a}, r{b} -> r{d}",style=filled,fillcolor={color}];')
        out.append(f'{"s"+str(a) if l is None else "n"+str(l)} -> n{i};')
        out.append(f'{"s"+str(b) if r is None else "n"+str(r)} -> n{i};')
    out.append('}'); path.write_text('\n'.join(out)+'\n')

def graph_opportunities(program, protected):
    nodes, snapshots = replay(program)
    required=[]; seen=set(STARTS)&protected
    for i,n in enumerate(nodes):
        if n[0] in protected and n[0] not in seen: required.append(i); seen.add(n[0])
    def closure(rewrite=None):
        kept=set(); stack=required[:]
        while stack:
            i=stack.pop()
            if i in kept: continue
            kept.add(i)
            deps = rewrite[1] if rewrite and i == rewrite[0] else nodes[i][1:3]
            stack.extend(d for d in deps if d is not None and d >= 0)
        return kept
    original=closure(); values={v:[-1-j] for j,v in enumerate(STARTS)}; candidates=[]
    for i,n in enumerate(nodes):
        target=n[0]
        if i in original and target in protected:
            for av,ids in list(values.items()):
                opts=[('+',target-av),('-',av-target)]
                if target%av==0: opts.append(('*',target//av))
                if av%target==0: opts.append(('/',av//target))
                for op,bv in opts:
                    if bv not in values or evaluate(op,av,bv)!=target: continue
                    for a in ids[-1:]:
                        for b in values[bv][-1:]:
                            new=closure((i,(a,b))); gain=len(original)-len(new)
                            if gain>0:
                                candidates.append({'target':target,'at_step':i+1,'formula':f'{av} {op} {bv}', 'source_steps':[a+1 if a>=0 else 0,b+1 if b>=0 else 0], 'graph_nodes_saved_if_schedulable':gain,'both_inputs_live':av in snapshots[i] and bv in snapshots[i]})
        values.setdefault(target,[]).append(i)
    return sorted(candidates,key=lambda x:(-x['graph_nodes_saved_if_schedulable'],x['at_step']))[:5]

def main():
    p=argparse.ArgumentParser(); p.add_argument('baseline',type=Path); p.add_argument('--id', default='scored_0810', choices=['scored_0810','scored_0001']); p.add_argument('--official', action='store_true'); args=p.parse_args()
    global STARTS, LIMIT
    if args.id == 'scored_0001': STARTS, LIMIT = [631, 889, 1205, 1563], 1445817928925762
    csv.field_size_limit(1000000)
    with args.baseline.open(newline='') as f: program=json.loads(next(x for x in csv.DictReader(f) if x['id']==args.id)['program'])
    manual=json.loads((ROOT/('experiments/scored_0810_shared_factor_program.json' if args.id == 'scored_0810' else 'experiments/scored_0001_anchor_program.json')).read_text())
    base_nodes,_=replay(program); manual_nodes,_=replay(manual)
    # All actual targets are historically covered by both programs. Preserve their
    # whole value-set intersection; it is a conservative superset of the targets.
    protected=({x[0] for x in base_nodes}|set(STARTS)) & ({x[0] for x in manual_nodes}|set(STARTS))
    if args.official:
        with (ROOT/'data/puzzles.csv').open(newline='') as f:
            official=next(row for row in csv.DictReader(f) if row['id']==args.id)
        if json.loads(official['starting_values']) != STARTS or int(official['value_limit']) != LIMIT: raise ValueError('puzzle mismatch')
        protected=set(json.loads(official['targets']))
    initial=prune(program,protected); current=initial; changes=[]
    while True:
        nodes,snaps=replay(current); best=None
        for i, node in enumerate(nodes):
            value=node[0]; regs=snaps[i]; dest=node[6]
            indices={}
            for j,v in enumerate(regs):
                if v is not None: indices.setdefault(v, []).append(j)
            candidates=[]
            for a,x in enumerate(regs):
                if x is None: continue
                possibilities=[('+',value-x),('-',x-value)]
                if value % x == 0: possibilities.append(('*',value//x))
                if x % value == 0: possibilities.append(('/',x//value))
                for op,y in possibilities:
                    for b in indices.get(y,[]): candidates.append((op,a,b,y))
            for op,a,b,y in candidates:
                if [op,a,b,dest]==current[i] or evaluate(op,regs[a],y)!=value: continue
                trial=current.copy(); trial[i]=[op,a,b,dest]
                try: trial=prune(trial,protected)
                except ValueError: continue
                gain=len(current)-len(trial)
                if gain>0 and (best is None or gain>best[0]): best=(gain,trial,{'step':i+1,'value':value,'old':current[i],'new':[op,a,b,dest],'inputs':[regs[a],y]})
        if not best: break
        gain,current,detail=best; detail['saved']=gain; changes.append(detail)
    puzzle={'starting_values':json.dumps(STARTS),'targets':json.dumps(sorted(protected)),'registers':48,'value_limit':LIMIT}
    validate(puzzle,program); validate(puzzle,current)
    suffix='_official' if args.official else ''
    dot(program,protected,ROOT/f'experiments/graph_{args.id}{suffix}_baseline.dot')
    dot(current,protected,ROOT/f'experiments/graph_{args.id}{suffix}_candidate.dot')
    report={'baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),'baseline_steps':len(program),'protected_values':sorted(protected),'pruned_steps':len(initial),'candidate_steps':len(current),'changes':changes,'candidate_program':current, 'graph_opportunities':graph_opportunities(program,protected)}
    (ROOT/f'experiments/graph_{args.id}{suffix}_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='candidate_program'},indent=2))
if __name__=='__main__': main()
