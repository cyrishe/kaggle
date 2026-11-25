"""Price blind shifted-GCD candidates by replaying whole-program rewrites on a held portfolio."""
import csv
import json
from baseline_lineage import DEFAULT_PUZZLES, DB, shallow
from first_solver import validate
from hybrid_graph_search import program_rules, rooted_rules, compile_changes
from benchmark_hybrid_graph import load_reference


def repair(p, initial, ranked):
    starts=json.loads(p['starting_values'])
    goals=json.loads(p['targets'])
    limit=int(p['value_limit'])
    book,_=shallow(starts,limit,2)
    original={}
    for rule in program_rules(p,initial):
        if rule[3] not in starts:
            original.setdefault(rule[3],rule)
    order=sorted(goals,key=lambda v:list(original).index(v) if v in original else -1)
    def compile_graph(graph):
        try:
            seq=rooted_rules(starts,order,graph)
        except ValueError:
            return None
        return compile_changes(p,seq,goals)
    normalized=compile_graph(original)
    control=min((v for v in (initial,normalized) if v is not None),key=len)
    best=control
    witness=None
    for _,_,f in ranked:
        for base in (4,16,32):
            graph=original.copy()
            def make(v):
                if v in starts or v in graph:
                    return
                if v in book:
                    rule=book[v]
                elif v<=base:
                    rule=('+',v-1,1,v) if v%2 else ('+',v//2,v//2,v)
                elif v%base==0:
                    rule=('*',v//base,base,v)
                else:
                    rem=v%base
                    if rem>base//2 and v+base-rem<=limit:
                        rule=('-',v+base-rem,base-rem,v)
                    else:
                        rule=('+',v-rem,rem,v)
                graph[v]=rule
                make(rule[1])
                make(rule[2])
            make(f)
            patches={}
            for t in goals:
                q,r=divmod(t,f)
                if r>2:
                    r-=f
                    q+=1
                if abs(r)>2 or q<2 or q*f>limit or t in starts:
                    continue
                make(q)
                mul=('*',f,q,q*f)
                rules=[mul]
                if r:
                    make(abs(r))
                    rules.append(('+' if r>0 else '-',q*f,abs(r),t))
                patches[t]=rules
            group=graph.copy()
            for patch in patches.values():
                group.update((s[3],s) for s in patch)
            proposal=compile_graph(group)
            if proposal is not None and len(proposal)<len(best):
                best,witness=proposal,dict(f=f,targets=list(patches))
            # The factor is optional for each consumer; accept individually profitable edits too.
            chosen=[]
            local=len(control)
            for t,patch in patches.items():
                group=graph.copy()
                group.update((s[3],s) for s in patch)
                proposal=compile_graph(group)
                if proposal is not None and len(proposal)<local:
                    chosen.append(t)
                    graph=group
                    local=len(proposal)
                    if local<len(best):
                        best,witness=proposal,dict(f=f,targets=chosen.copy())
    validate(p,best)
    return dict(initial=len(initial),control=len(control),best=len(best),witness=witness,
                program=best if len(best)<len(control) else None)


if __name__=='__main__':
    with DEFAULT_PUZZLES.open() as fd:
        ps={p['id']:p for p in csv.DictReader(fd)}
    candidates=json.loads(DB.with_name('target_multiplier_scan.json').read_text())
    cases=json.loads(DB.with_name('hybrid_graph_results.json').read_text())['cases']
    out={}
    for c in cases:
        i=c['id']
        out[i]={name:repair(ps[i],program,candidates[i]['top']) for name,program in
                 [('own',c['own_final_program']),('public',load_reference(i))]}
    DB.with_name('target_multiplier_rewrites.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    for name in ('own','public'):
        print(name, [sum(r[name][k] for r in out.values()) for k in ('initial','control','best')])
        print([(i,r[name]['control'],r[name]['best'],r[name]['witness']) for i,r in out.items() if r[name]['witness']])
