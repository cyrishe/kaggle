"""Measure input-value frequencies on the instruction DAG of each first-hit target."""
import json
import sqlite3
from collections import Counter, deque
from statistics import median

from baseline_lineage import DB


def analyze_puzzle(ident, targets, rows, coverage_top_k=3):
    values = {s: v for s, v, _, _ in rows}
    parents = {s: (l, r) for s, _, l, r in rows if l is not None}
    starts = {v for s, v, _, _ in rows if s < 0}
    first = {}
    for s, v, _, _ in rows:
        first.setdefault(v, s)
    actual_reads = Counter(values[p] for pair in parents.values() for p in pair)
    coverage = Counter()
    near = Counter()
    cumulative_reads = Counter()
    leaders = Counter()
    results = []
    for goal in targets:
        queue = deque([(first[goal], 0)])
        visited = set()
        counts = Counter()
        near_values = set()
        while queue:
            s, distance = queue.popleft()
            if s in visited or s not in parents:
                continue
            visited.add(s)
            for p in parents[s]:
                counts[values[p]] += 1
                if distance < 2:
                    near_values.add(values[p])
                queue.append((p, distance+1))
        assert sum(counts.values()) == 2*len(visited)
        coverage.update(counts.keys())
        near.update(near_values)
        cumulative_reads.update(counts)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if ranked:
            leaders.update(v for v,n in ranked if n==ranked[0][1])
        results.append(dict(target=goal,instructions=len(visited),top3=ranked[:3],
                            tie_at_cutoff=(len(ranked)>3 and ranked[2][1]==ranked[3][1])))
    def value_info(v):
        return dict(value=v, targets=coverage[v], final_two=near[v],
                    program_reads=actual_reads[v], lineage_reads=cumulative_reads[v])
    ranked = sorted(coverage,key=lambda v:(-coverage[v],-actual_reads[v],v))
    close_ranked = sorted(near,key=lambda v:(-near[v],-actual_reads[v],v))
    helpers = [v for v in ranked if v not in starts and v not in targets]
    big_helpers = [v for v in helpers if v>max(starts)]
    return dict(id=ident,n=len(targets),steps=len(parents),per_target=results,
                by_coverage=[value_info(v) for v in ranked[:coverage_top_k]],
                most_program_reads=[value_info(v) for v in sorted(actual_reads,key=lambda v:(-actual_reads[v],v))[:3]],
                per_target_leaders=sorted(leaders.items(),key=lambda p:(-p[1],p[0]))[:3],
                pure_helpers=[value_info(v) for v in helpers[:3]],
                large_helpers=[value_info(v) for v in big_helpers[:3]],
                by_final_two=[value_info(v) for v in close_ranked[:3]],
                full_coverage_values=sum(coverage[v]==len(targets) for v in ranked),
                full_coverage_large_helpers=sum(coverage[v]==len(targets) for v in big_helpers))


if __name__ == '__main__':
    cases=[]
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as c:
        meta=dict(c.execute('select key,value from metadata'))
        for ident, serialized in c.execute('select id,targets from puzzles order by id'):
            rows=c.execute('select step,value,left_step,right_step from nodes where puzzle=? order by step',(ident,)).fetchall()
            cases.append(analyze_puzzle(ident,json.loads(serialized),rows))
    def stats(items):
        def rank_summary(name,k):
            represented=[r[name][k]['targets' if name!='by_final_two' else 'final_two']/r['n']
                         if len(r[name])>k else 0 for r in items]
            return dict(median=median(represented),all=sum(v==1 for v in represented),
                        at_least_half=sum(v>=0.5 for v in represented))
        return dict(puzzles=len(items),targets=sum(r['n'] for r in items),
                    ranks={key:[rank_summary(key,k) for k in range(3)]
                           for key in ('by_coverage','large_helpers','by_final_two')})
    output=dict(source=meta,all=stats(cases),exactly_32=stats([r for r in cases if r['n']==32]),cases=cases)
    path=DB.with_name('target_reuse_frequency.json')
    path.write_text(json.dumps(output,separators=(',',':'))+'\n')
    print(json.dumps({k:output[k] for k in ('all','exactly_32')},indent=1))
    case=next(r for r in cases if r['id']=='scored_0001')
    print({k:v for k,v in case.items() if k!='per_target'})
    for r in case['per_target']:
        print('|',r['target'],'|',r['instructions'],'|',' | '.join(f'{v} ({n})' for v,n in r['top3']),'|')
