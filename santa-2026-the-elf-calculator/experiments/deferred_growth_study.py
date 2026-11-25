"""Query official targets and target differences using a complete two-layer cache."""
import csv
import json
import subprocess
import tempfile
from collections import Counter
from itertools import combinations
from pathlib import Path

from depth_graph_study import DEFAULT_PUZZLES, ROOT, shallow


def probe(binary,limit,book,queries):
    lines=[f'{limit} {len(book)} 0 0 {len(queries)}',' '.join(map(str,book))]
    lines.extend(f'{v} 0' for v in queries)
    run=subprocess.run([str(binary),'--defer-slow'],input='\n'.join(lines)+'\n',text=True,
                       capture_output=True,check=True)
    values={}
    for line in run.stdout.splitlines():
        t,status,*recipe=line.split()
        t=int(t)
        if recipe:
            op=recipe[0]
            a,b=map(int,recipe[1:])
            if a not in book or b not in book:raise ValueError('operand missing')
            if op=='/' and a%b:raise ValueError('inexact division')
            if {'=':a,'+':a+b,'-':a-b,'*':a*b,'/':a//b}[op]!=t:raise ValueError('bad witness')
            slow=(max(a,b)<t and 100*t<=105*max(a,b))
            if (status=='resumed')!=slow:raise ValueError('incorrect slow label')
        values[t]=(status,recipe)
    return values


def main():
    stats={k:Counter() for k in ('targets','distinct_differences')}
    examples=[]
    affected=Counter()
    detail={}
    with tempfile.TemporaryDirectory() as tmp,DEFAULT_PUZZLES.open() as f:
        binary=Path(tmp)/'query'
        subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('sparse_depth_query.cpp')),
                        '-o',str(binary)],check=True)
        for p in csv.DictReader(f):
            limit=int(p['value_limit'])
            goals=json.loads(p['targets'])
            book,_=shallow(json.loads(p['starting_values']),limit,2)
            groups={'targets':set(goals),'distinct_differences':{b-a for a,b in combinations(sorted(set(goals)),2)}}
            hits=probe(binary,limit,book,sorted(set.union(*groups.values())))
            counts={}
            for name,items in groups.items():
                count=Counter(hits[v][0] for v in items)
                counts[name]=dict(count)
                stats[name].update(count)
                if count['resumed']:affected[name]+=1
                if count['resumed'] and len(examples)<30:
                    target=next(v for v in sorted(items) if hits[v][0]=='resumed')
                    examples.append(dict(id=p['id'],kind=name,value=target,recipe=hits[target][1]))
            detail[p['id']]=counts
    summary=dict(stats=stats,affected_puzzles=affected,examples=examples,cases=detail)
    (ROOT/'reports/deferred_growth_study.json').write_text(json.dumps(summary,separators=(',',':'))+'\n')
    print(stats,affected,examples[:5])


if __name__=='__main__':
    main()
