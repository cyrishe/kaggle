"""List every non-initial value >= 10 used by every target's first-hit lineage."""
import json
import random
import sqlite3
from collections import Counter
from statistics import median

from target_reuse_frequency import DB, analyze_puzzle


def summarize(cases):
    counts = [len(c['values']) for c in cases]
    reads = [v['program_reads'] for c in cases for v in c['values']]
    tens = sum(any(v['value'] == 10 for v in c['values']) for c in cases)
    return dict(puzzles=len(cases), occurrences=sum(counts), mean=sum(counts)/len(counts),
                median=median(counts), histogram=dict(sorted(Counter(counts).items())),
                distinct_values=len({v['value'] for c in cases for v in c['values']}),
                strict_gt10_occurrences=sum(counts)-tens, tens=tens,
                median_program_reads=median(reads), read_once=reads.count(1))


def main():
    cases = []
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        for ident, targets in conn.execute('SELECT id,targets FROM puzzles ORDER BY id'):
            rows = conn.execute('SELECT step,value,left_step,right_step FROM nodes WHERE puzzle=? ORDER BY step',(ident,)).fetchall()
            starts = {v for s,v,_,_ in rows if s<0}
            roots = json.loads(targets)
            stats = analyze_puzzle(ident, roots, rows, coverage_top_k=len(rows))
            eligible = [e for e in stats['by_coverage'] if e['value']>=10 and e['value'] not in starts]
            full = [e for e in eligible if e['targets']==len(roots)]
            next_count = next((e['targets'] for e in eligible if e['targets']<len(roots)),None)
            cases.append(dict(id=ident, targets=len(roots), values=full, next_coverage=next_count))
    sample_ids = set(random.Random(20261125).sample([r['id'] for r in cases],100))
    sample = [r for r in cases if r['id'] in sample_ids]
    result = dict(sample_seed=20261125,sample_ids=sorted(sample_ids),
                  sample_summary=summarize(sample),all_summary=summarize(cases),cases=cases)
    DB.with_name('full_coverage_helpers.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    lines = ['# 100 道计分题中被全部目标用到的非初始数','',
             '数值 ≥ 10。沿每个目标首次命中的指令回溯，作为操作数出现即计入该目标。每个数在同一题只列一次。'
             '表内每个数均覆盖该行的全部目标，同覆盖数按整题读取次数降序、数值升序排列。','',
             '| 题号 | 目标数 | 满覆盖数字个数 | 完整数字列表 | 下一数字的覆盖数 |','|---|---:|---:|---|---:|']
    for r in sample:
        numbers = '、'.join(str(e['value']) for e in r['values']) or '无'
        lines.append(f"| {r['id']} | {r['targets']} | {len(r['values'])} | {numbers} | {r['next_coverage'] or '无'} |")
    DB.with_name('sample_100_full_coverage_helpers.md').write_text('\n'.join(lines)+'\n')
    print(result['sample_summary'],result['all_summary'],sep='\n')


if __name__=='__main__':
    main()
