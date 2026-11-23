#!/usr/bin/env python3
"""Construct and independently replay a positional-base program for one puzzle."""
import csv, json, argparse, math
from pathlib import Path

def build(puzzle, base):
    starts=json.loads(puzzle['starting_values']); targets=json.loads(puzzle['targets'])
    if len(starts)+base+1>48: raise ValueError('not enough registers')
    ops=[]; offset=len(starts); unit=offset
    ops.append(['/',0,0,unit])
    regs={1:unit}
    for n in range(2,base+1):
        regs[n]=offset+n-1
        ops.append(['+',regs[n-1],unit,regs[n]])
    acc=offset+base
    if acc+2>=48: raise ValueError('not enough scratch registers')
    def encode(n,dest):
        digits=[]
        while n: n,rem=divmod(n,base); digits.append(rem)
        digits.reverse(); out=[]; current=regs[digits[0]]
        if len(digits)==1:
            return [['*',current,unit,dest]]
        for digit in digits[1:]:
            out.append(['*',current,regs[base],dest]); current=dest
            if digit: out.append(['+',dest,regs[digit],dest])
        return out
    for t in targets:
        if t in starts or t<=base: continue
        choices=[encode(t,acc)]
        root=math.isqrt(t)
        for k in (root,root+1):
            square=k*k
            if k<1 or square>int(puzzle['value_limit']): continue
            delta=abs(t-square)
            trial=encode(k,acc)+[['*',acc,acc,acc]]
            if delta:
                trial+=encode(delta,acc+1)
                trial.append(['+' if square<t else '-',acc,acc+1,acc+2])
            choices.append(trial)
        ops.extend(min(choices,key=len))
    return ops

def validate(puzzle,ops):
    starts=json.loads(puzzle['starting_values']); targets=set(json.loads(puzzle['targets']))
    limit=int(puzzle['value_limit']); values=starts+[None]*(int(puzzle['registers'])-len(starts)); covered=set(starts)&targets
    for step,(op,i,j,d) in enumerate(ops,1):
        if any(not isinstance(k,int) or not 0<=k<len(values) for k in (i,j,d)): raise ValueError(f'bad register at {step}')
        a,b=values[i],values[j]
        if a is None or b is None: raise ValueError(f'undefined register at {step}')
        if op=='+': v=a+b
        elif op=='-': v=a-b
        elif op=='*': v=a*b
        elif op=='/':
            if b==0 or a%b: raise ValueError(f'inexact division at {step}')
            v=a//b
        else: raise ValueError(f'bad operation at {step}')
        if not 1<=v<=limit: raise ValueError(f'value {v} outside bounds at {step}')
        values[d]=v
        if v in targets: covered.add(v)
    missing=targets-covered
    if missing: raise ValueError(f'missing targets: {missing}')
    encoded=json.dumps(ops,separators=(',',':'))
    if len(ops)>4096 or len(encoded.encode())>131072: raise ValueError('program limit exceeded')
    return len(ops),len(encoded.encode()),len(covered)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--id',default='scored_0001'); args=ap.parse_args()
    with open('data/puzzles.csv',newline='') as f: puzzle=next(r for r in csv.DictReader(f) if r['id']==args.id)
    candidates=[]
    for b in range(2, min(40,int(puzzle['value_limit']),47-len(json.loads(puzzle['starting_values'])))+1):
        try:
            p=build(puzzle,b); result=validate(puzzle,p); candidates.append((len(p),b,p,result))
        except ValueError: pass
    count,base,program,result=min(candidates,key=lambda x:x[0])
    Path('experiments').mkdir(exist_ok=True)
    path=Path('experiments')/(args.id+'_program.json');path.write_text(json.dumps(program,separators=(',',':'))+'\n')
    print(f'id={args.id} base={base} steps={count} bytes={result[1]} targets={result[2]} output={path}')
    print('best bases',[(x[1],x[0]) for x in sorted(candidates,key=lambda x:x[0])[:8]])
if __name__=='__main__':main()
