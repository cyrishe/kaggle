"""Relate operator choice and helper creation/use to the relative DAG depth of a puzzle."""
import json
import sqlite3
from collections import Counter, defaultdict
from statistics import median
from baseline_lineage import DB

OPS = ('+', '*', '-', '/')


def band(depth, maximum):
    return max(0,(4*depth-1)//maximum)


def table():
    return [Counter() for _ in range(4)]


def accumulate(puzzles):
    totals = defaultdict(table)
    comparison = defaultdict(Counter)
    differences = defaultdict(list)
    helper_birth = []
    helper_use = []
    helper_count = 0
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as con:
        for p in puzzles:
            ident = p['id']
            maximum, goals = con.execute('SELECT max_depth,targets FROM puzzles WHERE id=?',(ident,)).fetchone()
            goals = set(json.loads(goals))
            counts = defaultdict(table)
            helper_values = {r['value'] for r in p['values']}
            helper_count += len(helper_values)
            nodes = {}
            seen = set()
            for step,v,d,op,a,b in con.execute('SELECT step,value,depth,op,left_step,right_step FROM nodes WHERE puzzle=? ORDER BY step',(ident,)):
                nodes[step] = (v,d)
                if op is not None:
                    assert d == 1+max(nodes[a][1],nodes[b][1])
                    i = band(d,maximum)
                    counts['all'][i][op] += 1
                    category = 'target_first_hit' if v in goals and v not in seen else 'other'
                    counts[category][i][op] += 1
                    if min(nodes[a][1],nodes[b][1])*2 <= maximum:
                        counts[category+'_shallow_operand'][i][op] += 1
                    if v in helper_values and v not in seen:
                        counts['helper_first_creation'][i][op] += 1
                        helper_birth.append(d/maximum)
                    touches_helper = False
                    for parent in (a,b):
                        value, source_depth = nodes[parent]
                        if value in helper_values:
                            touches_helper = True
                            counts['helper_reads'][i][op] += 1
                            counts['helper_read_source_depth'][band(source_depth,maximum)][op] += 1
                            counts['source_vs_read'][band(source_depth,maximum)][i] += 1
                            helper_use.append(d/maximum)
                    if touches_helper:
                        counts['helper_instructions'][i][op] += 1
                seen.add(v)
            assert max(d for _,d in nodes.values()) == maximum
            for name,rows in counts.items():
                for k,row in enumerate(rows):
                    totals[name][k].update(row)
            for name in ('all','other','helper_reads'):
                rows = counts[name]
                early, late = rows[0]+rows[1], rows[2]+rows[3]
                n,m = sum(early.values()),sum(late.values())
                if n and m:
                    for op in OPS:
                        change = late[op]*n-early[op]*m
                        comparison[name,op]['up' if change>0 else 'down' if change<0 else 'tie'] += 1
                        differences[name,op].append(100*change/(m*n))
    return dict(puzzles=len(puzzles),helpers=helper_count,by_band=totals,
                birth_median=median(helper_birth),read_median=median(helper_use),
                within_puzzle={k:{op:dict(comparison[k,op],median_difference_pp=median(differences[k,op]))
                                  for op in OPS} for k in ('all','other','helper_reads')})


if __name__=='__main__':
    helpers = json.loads(DB.with_name('full_coverage_helpers.json').read_text())
    sample = set(helpers['sample_ids'])
    out = dict(all=accumulate(helpers['cases']),sample=accumulate([r for r in helpers['cases'] if r['id'] in sample]))
    previous = json.loads(DB.with_name('shared_value_operations.json').read_text())
    for group,c in out.items():
        for op in OPS:
            for name,column in [('all','all_instructions'),('helper_reads','reads'),('helper_instructions','instructions')]:
                assert sum(row[op] for row in c['by_band'][name]) == previous[group][op][column]
            for i in range(4):
                assert c['by_band']['all'][i][op] == c['by_band']['target_first_hit'][i][op]+c['by_band']['other'][i][op]
        assert sum(map(lambda r:sum(r.values()), c['by_band']['helper_first_creation'])) == c['helpers']
    DB.with_name('relative_depth_operations.json').write_text(json.dumps(out,indent=2)+'\n')
