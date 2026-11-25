"""Report how many distinct first-hit target lineages read each of the top five values."""
import json
import random
import sqlite3
from target_reuse_frequency import analyze_puzzle, DB

SEED = 20261125
with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro', uri=True) as db:
    targets = dict(db.execute('SELECT id, targets FROM puzzles ORDER BY id'))
    ids = sorted(random.Random(SEED).sample(sorted(targets), 100))
    lines = ['# 100 道随机计分题的数字覆盖数', '',
             '种子 20261125。样本来自总分 132,255 的公开解。括号内是使用该数字的不同目标个数。'
             '包含初始数；对每个目标的首次命中按操作数血缘回溯，每个数字只计一次。'
             '覆盖数相同时，整题实际读取次数多的排在前面，再按数值升序。', '',
             '| 题号 | 目标数 | 前五个数字（覆盖数） |',
             '|---|---:|---|']
    full = [0]*5
    total_goals = 0
    for ident in ids:
        goals = json.loads(targets[ident])
        rows = db.execute('SELECT step,value,left_step,right_step FROM nodes WHERE puzzle=? ORDER BY step',(ident,)).fetchall()
        summary = analyze_puzzle(ident,goals,rows,coverage_top_k=5)
        top = summary['by_coverage']
        total_goals += len(goals)
        for rank, entry in enumerate(top):
            full[rank] += entry['targets']==len(goals)
        entries = '、'.join(f"{e['value']}({e['targets']})" for e in top)
        lines.append(f'| {ident} | {len(goals)} | {entries} |')
    lines += ['', f'共 {total_goals} 个题内目标。五个名次各自覆盖全部目标的题数依次为 {full}。']
    DB.with_name('sample_100_target_coverage.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
