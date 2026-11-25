"""Check whether the input-selected factors are used by the archived public program."""
import json
import sqlite3
from collections import defaultdict

from baseline_lineage import DB


def check(connection, ident, groups):
    rows = connection.execute(
        'SELECT step,value,op,left_step,right_step FROM nodes WHERE puzzle=? ORDER BY step',(ident,)
    ).fetchall()
    goals, = connection.execute('SELECT targets FROM puzzles WHERE id=?',(ident,)).fetchone()
    goals = json.loads(goals)
    targets = {v:1<<i for i,v in enumerate(goals)}
    first, values = {}, {}
    for s,v,*_ in rows:
        first.setdefault(v,s)
        values[s] = v
    mask = defaultdict(int)
    for v,bit in targets.items():
        mask[first[v]] |= bit
    wanted = {f for f,_,_ in groups}
    reached = defaultdict(int)
    for s,v,op,a,b in reversed(rows):
        if not op or not mask[s]:
            continue
        mask[a] |= mask[s]
        mask[b] |= mask[s]
        if op=='*':
            for f in wanted.intersection((values[a],values[b])):
                reached[f] |= mask[s]
    result = []
    for f,_,members in groups:
        matched = [t for t in members if targets[t]&reached[f]]
        result.append(dict(f=f,size=len(members),matched=len(matched),descendants=bin(reached[f]).count('1')))
    return result


if __name__=='__main__':
    report = json.loads(DB.with_name('factor_routing.json').read_text())['cases']
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        stats = {i:check(conn,i,r['exact'] or r['relaxed']) for i,r in report.items() if r['relaxed']}
    DB.with_name('factor_routing_lineage.json').write_text(json.dumps(stats,separators=(',',':'))+'\n')
    for label in ('factor','weak_factor'):
        subset = [v for i,v in stats.items() if report[i]['route']==label]
        print(label,len(subset),[sum(any(row['matched']>=n for row in rs) for rs in subset) for n in (1,2,3)],
              sum(any(r['matched']==r['size'] for r in rs) for rs in subset))
