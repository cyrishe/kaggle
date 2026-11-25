"""Compare exact inverse tests, bounded anchor search and decreasing quotient search."""
import json
import resource
import sys
import subprocess
import tempfile
from itertools import combinations
from pathlib import Path

from depth_graph_study import ROOT, DEFAULT_PUZZLES, rules, dag
from probe_baseline_pair import read_case, compile_values


def limited_layers(starts,limit,pair_budget=1_000_000,value_budget=16_384):
    """Only commit complete layers; test each unordered pair in its first eligible layer."""
    book=dict.fromkeys(starts)
    counts=[len(book)]
    old_count=0
    while True:
        entries=list(book)
        n=len(entries)
        pairs=(n*(n+1)-old_count*(old_count+1))//2
        if pairs>pair_budget:
            return book,counts,dict(reason='pair_budget',next_new_pairs=pairs)
        pending={}
        for j in range(old_count,n):
            for i in range(j+1):
                a,b=sorted((entries[i],entries[j]))
                for op,x,y,v in rules(a,b,limit):
                    if 0<v<=limit and v not in book and v not in pending:
                        if n+len(pending)>=value_budget:
                            return book,counts,dict(reason='value_budget',next_new_pairs=pairs)
                        pending[v]=(op,x,y,v)
        if not pending:
            return book,counts,dict(reason='exhausted',next_new_pairs=0)
        old_count=n
        book.update(pending)
        counts.append(len(book))


def dependencies(book):
    supports={}
    for v,rule in book.items():
        supports[v]=frozenset() if rule is None else supports[rule[1]]|supports[rule[2]]|{v}
    return supports


def compile_graph(p,book,goals):
    seen=set(json.loads(p['starting_values']))
    active=set()
    sequence=[]
    def emit(v):
        if v in seen:
            return
        if v in active:
            raise ValueError('cycle')
        active.add(v)
        rule=book[v]
        emit(rule[1])
        emit(rule[2])
        sequence.append(rule)
        active.remove(v)
        seen.add(v)
    for t in goals:
        emit(t)
    return compile_values(p,sequence,goals)


def run_queries(binary,limit,keys,queries,budget,begin=0):
    data=[f'{limit} {len(keys)} {begin} {budget} {len(queries)}',' '.join(map(str,keys))]
    data.extend(f'{t} {int(deep)}' for t,deep in queries)
    result=subprocess.run([str(binary)],input='\n'.join(data)+'\n',text=True,capture_output=True,check=True)
    hits={}
    for line in result.stdout.splitlines():
        target,count,*r=line.split()
        if int(count):
            hits[int(target)]=[(r[j],*map(int,r[j+1:j+4])) for j in range(0,len(r),4)]
    queries,scans,peak_bytes=map(int,result.stderr.split())
    return hits,dict(membership_calls=queries,operand_checks=scans,native_peak_bytes=peak_bytes)


def summarize(p,program):
    nodes=dag(p,program)
    return dict(steps=len(program),depth=max(n['depth'] for n in nodes),
                register_count=len({r for op in program for r in op[1:]}),program=program)


def connect(hits,edges,found,recipes):
    reached=set(hits)
    for u,v in edges:
        for op,a,b,value in found[v-u]:
            if op!='=':recipes.setdefault(value,(op,a,b,value))
    while True:
        before=len(reached)
        for u,v in edges:
            if u in reached and v not in reached:
                recipes[v]=('+',u,v-u,v)
                reached.add(v)
            elif v in reached and u not in reached:
                recipes[u]=('-',v,v-u,u)
                reached.add(u)
        if before==len(reached):break
    return reached


def adaptive(binary,p,book,keys,targets,edges,found):
    limit=int(p['value_limit'])
    recipes=dict(book)
    reached=set()
    stages=[]
    begin=0
    for end in (8,32,128,512,1024):
        missing=sorted(set(targets)-reached)
        hits,info=run_queries(binary,limit,keys,[(t,True) for t in missing],end,begin)
        for path in hits.values():
            for op,a,b,v in path:
                if op!='=':recipes.setdefault(v,(op,a,b,v))
        reached=connect(reached|hits.keys(),edges,found,recipes)
        stages.append(dict(begin=begin,end=end,goals_probed=len(missing),reached=len(reached),**info))
        if len(reached)==len(targets):
            program=compile_graph(p,recipes,targets)
            program=improve_links(p,recipes,targets,edges,found,program)
            return dict(stages=stages,stop='all_goals',**summarize(p,program))
        if end>=32 and not reached and not edges:
            return dict(stages=stages,stop='no_direct_or_conditional_hit')
        begin=end
    return dict(stages=stages,stop='anchor_cap')


def improve_links(p,book,targets,edges,hits,program):
    # Compare validated single replacements; iterate only on strict whole-program gains.
    roots=dict(book)
    for a,b in edges:
        for op,x,y,v in hits[b-a]:
            if op!='=':
                roots.setdefault(v,(op,x,y,v))
    while True:
        winner=None
        for a,b in edges:
            for change in [('+',a,b-a,b),('-',b,b-a,a)]:
                try:
                    next_program=compile_graph(p,roots|{change[3]:change},targets)
                except ValueError as err:
                    if str(err) not in ('cycle','register budget exceeded'):
                        raise
                    continue
                if len(next_program)<len(program) and (winner is None or len(next_program)<len(winner[1])):
                    winner=change,next_program
        if winner is None:
            return program
        change,program=winner
        roots[change[3]]=change


def quotient_plan(p,shallow_book,supports,targets):
    """One path per target for each fixed base. Test only exact signed residue classes."""
    limit=int(p['value_limit'])
    bases=sorted({2,4,8,16,31,32,63,64,126,127,128,255,256,512,1024,1711} & shallow_book.keys())
    best=None
    logs=[]
    for base in bases:
        book=dict(shallow_book)
        digits={}
        for r in book:
            if r<=2*base:
                digits.setdefault(r%base,[]).append(r)
                digits.setdefault((-r)%base,[]).append(-r)
        def build(t):
            if t in book:return True
            candidates=[]
            for r in [0]+digits.get(t%base,[]):
                product=t-r
                if product<=0 or product>limit or product%base:continue
                q=product//base
                if not 0<q<t:continue
                # Estimate the current cost of the remainder and the quotient.
                digit_cost=len(supports[abs(r)]) if r else 0
                q_cost=0 if q in book else q.bit_length()
                candidates.append((digit_cost+(r!=0)+q_cost,abs(r),q,r))
            for _,_,q,r in sorted(candidates):
                if not build(q):continue
                product=t-r
                if product not in book:book[product]=('*',base,q,product)
                if r:book[t]=('+' if r>0 else '-',product,abs(r),t)
                return True
            return False
        if not all(build(t) for t in targets):
            logs.append([base,'uncovered'])
            continue
        try:
            program=compile_graph(p,book,targets)
        except ValueError as err:
            if str(err) not in ('cycle','register budget exceeded'):raise
            logs.append([base,str(err)])
            continue
        logs.append([base,len(program)])
        if best is None or len(program)<len(best[1]):
            best=(base,program)
    return dict(trials=logs,base=best[0],**summarize(p,best[1])) if best else dict(trials=logs)


def study(binary,ident):
    p=read_case(DEFAULT_PUZZLES,ident)
    starts=json.loads(p['starting_values'])
    targets=json.loads(p['targets'])
    limit=int(p['value_limit'])
    book,counts,stop=limited_layers(starts,limit)
    supports=dependencies(book)
    keys=sorted(book,key=lambda v:(len(supports[v]),v))
    pairs=list(combinations(targets,2))
    exact_queries=sorted(set(targets)|{b-a for a,b in pairs})
    found,exact=run_queries(binary,limit,keys,[(t,False) for t in exact_queries],0)
    edges=[(a,b) for a,b in pairs if b-a in found]
    exact.update(goals=[t for t in targets if t in found],edges=edges,query_count=len(exact_queries))
    result=dict(counts=counts,frontier_stop=stop,exact=exact,bounded={})
    for cap in ([8,32,128,512,1024] if ident=='scored_0253' else [8,32,128,512]):
        hits,info=run_queries(binary,limit,keys,[(t,True) for t in targets],cap)
        recipes=dict(book)
        for rules in hits.values():
            for op,a,b,v in rules:
                if op!='=':recipes.setdefault(v,(op,a,b,v))
        if hits:
            part=compile_graph(dict(p,targets=json.dumps(sorted(hits))),recipes,sorted(hits))
            info['partial_steps']=len(part)
        reached=connect(hits,edges,found,recipes)
        if reached:
            partial_puzzle=dict(p,targets=json.dumps(sorted(reached)))
            program=compile_graph(partial_puzzle,recipes,sorted(reached))
            usable=[(u,v) for u,v in edges if u in reached and v in reached]
            program=improve_links(partial_puzzle,recipes,sorted(reached),usable,found,program)
            info['with_links']=summarize(partial_puzzle,program)
        info['coverage_with_links']=len(reached)
        info['hits']=len(hits)
        result['bounded'][cap]=info
    result['adaptive']=adaptive(binary,p,book,keys,targets,edges,found)
    result['residue_plan']=quotient_plan(p,book,supports,targets)
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result['python_process_peak_bytes_to_date']=peak if sys.platform=='darwin' else peak*1024
    return result


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as temp:
        binary=Path(temp)/'query'
        src=Path(__file__).with_name('sparse_depth_query.cpp')
        subprocess.run(['c++','-O3','-std=c++17',str(src),'-o',str(binary)],check=True)
        result={}
        for ident in ('scored_0253','scored_0051'):
            item=study(binary,ident)
            result[ident]=item
            print(ident,item['counts'],item['exact'],flush=True)
            print([(k,v['hits'],v.get('partial_steps'),v.get('with_links',{}).get('steps')) for k,v in item['bounded'].items()],flush=True)
            print(item['residue_plan']['trials'],flush=True)
        (ROOT/'reports/sparse_depth_study.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
