"""Count operation types when reading the previously identified fully shared values."""
import json
import sqlite3
from collections import Counter
from baseline_lineage import DB


def count_case(connection, case):
    expected = {item['value']:item['program_reads'] for item in case['values']}
    per_value = {v:Counter() for v in expected}
    counts = Counter()
    values = {}
    for step, value, op, left, right in connection.execute(
            'SELECT step,value,op,left_step,right_step FROM nodes WHERE puzzle=? ORDER BY step', (case['id'],)):
        values[step] = value
        if op is None:
            continue
        a, b = values[left], values[right]
        shared_left, shared_right = a in expected, b in expected
        counts['all_instructions',op] += 1
        if shared_left:
            per_value[a][op] += 1
            counts['left',op] += 1
        if shared_right:
            per_value[b][op] += 1
            counts['right',op] += 1
        if shared_left or shared_right:
            counts['instructions',op] += 1
            counts['reads',op] += shared_left + shared_right
            counts['same_value',op] += a == b
    for v,operations in per_value.items():
        assert sum(operations.values()) == expected[v]
        for op in operations:
            counts['helpers_used',op] += 1
    return counts


def summarize(counts):
    return {op:{metric:counts[metric,op] for metric in
                ('reads','instructions','helpers_used','left','right','same_value','all_instructions')}
            for op in ('+','*','-','/')}


if __name__=='__main__':
    prior = json.loads(DB.with_name('full_coverage_helpers.json').read_text())
    sample_ids = set(prior['sample_ids'])
    summary, sample = Counter(), Counter()
    cases = {}
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as connection:
        for case in prior['cases']:
            result = count_case(connection,case)
            summary.update(result)
            if case['id'] in sample_ids:
                sample.update(result)
            cases[case['id']] = summarize(result)
    out = dict(sample=summarize(sample),all=summarize(summary),cases=cases)
    DB.with_name('shared_value_operations.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    for group in ('sample','all'):
        r=out[group]
        for op,c in r.items():
            print(group,op,c, 'read_pct', round(100*c['reads']/sum(v['reads'] for v in r.values()),2),
                  'other_read_pct',round(100*(2*c['all_instructions']-c['reads'])/sum(2*v['all_instructions']-v['reads'] for v in r.values()),2))
