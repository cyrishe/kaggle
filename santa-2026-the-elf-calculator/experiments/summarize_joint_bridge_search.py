"""Validate every independent candidate and report numerical-hint diagnostics separately."""
import csv
import json
from pathlib import Path
from collections import Counter
from baseline_lineage import ROOT, DEFAULT_PUZZLES
from benchmark_hybrid_graph import load_reference
from hybrid_graph_search import program_rules
from first_solver import validate

REPORTS=ROOT/'reports'
CLEAN=['joint_bridge_search','joint_bridge_holdout','joint_bridge_refinement','joint_bridge_catalog',
       'joint_bridge_frontier','joint_bridge_neighborhood','joint_bridge_exchange']
NAMES=['scored_0810','scored_0289','scored_0399','scored_0253','scored_0035','scored_0667']
def read(name):return json.loads((REPORTS/(name+'.json')).read_text())

def canonical(rule):
    op,a,b,v=rule
    return (op,min(a,b),max(a,b),v) if op in ('+','*') else rule

def main():
    with DEFAULT_PUZZLES.open() as file:puzzles={p['id']:p for p in csv.DictReader(file)}
    first={**read(CLEAN[0]),**read(CLEAN[1])}
    rows={}
    tested=0
    for name in CLEAN:
        for i,r in read(name).items():
            if r.get('inputs_only') is False or r.get('diagnostic'):
                raise ValueError('diagnostic run in independent list')
            programs=r['arms'] if 'arms' in r else {'repair':r}
            for arm,a in programs.items():
                prog=a['program'];tested+=1
                cost=validate(puzzles[i],prog)[0]
                assert cost==a['steps']
                if i not in rows or cost<rows[i]['steps']:
                    rows[i]=dict(steps=cost,source=name,method=arm,program=prog)
    for i,r in rows.items():
        p=puzzles[i];pub=load_reference(i)
        r['public']=validate(p,pub)[0]
        own=program_rules(p,r['program']);reference=program_rules(p,pub)
        start=set(json.loads(p['starting_values']));goals=set(json.loads(p['targets']))
        ov={s[-1] for s in own}-start-goals
        pv={s[-1] for s in reference}-start-goals
        r.update(targets=len(goals),own_helpers=len(ov),overlap_helpers=len(ov&pv),
                 overlap_rules=len(set(map(canonical,own))&set(map(canonical,reference))))
    (REPORTS/'joint_bridge_verified_programs.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
    wins=sum(r['steps']<r['public'] for r in rows.values())
    ties=sum(r['steps']==r['public'] for r in rows.values())
    text=['# 随机搜索中间数与整张计算图的联合删减','',
          f'44 道计分题。独立候选逐条回放共 {tested} 份，覆盖全部原目标并满足该题寄存器数、整除性和值域。逐题取最短后，严格短于存档公开解 {wins} 题，持平 {ties} 题。比较对象为存档的 132,255 步公开程序。','',
          '固定预算第一轮包括目标最大值在 (1,000, 100,000] 的全部 7 题、4 道历史诊断题、4 道沿用固定种子的抽样题，以及目标最大值在 (100,000, 1,000,000] 的全部 29 题。后续扩展与局部修复针对部分题增加了算力，汇总成绩逐题取短。','',
          '## 固定预算对照','',
          '| 44 题合计 | 指令数 |','|---|---:|']
    for key,label in [('tree','初始程序与确定性算式树取短'),('random_tree','只随机改变各数的构造代价'),('uniform_bridge','引入随机中间数与供体计算图，再联合删减'),('shared_bridge','同一流程，按候选中间数可服务的不同结果加权抽取')]:
        text.append(f"| {label} | {sum(r['arms'][key]['steps'] for r in first.values()):,} |")
    text+=['','后面三组每题每种策略均为 500 次候选提议，保留本组最短合法程序。不同提议的运算量不完全相同。首轮只从初始数和原目标生成候选字典，至多加入两个商分组的自主构造。随机价格用作提议分数，最后按真实算术指令数取舍。联合删减从现有图增加若干候选值与供体图，在该集合允许的全部算术关系中逐个试删中间数。每次删除均检验所有目标能否从初始数得到，最后调度并回放。','',
          '## 分题结果','',
          '| 题号 | 目标数 | 第一轮最短 | 所有独立试验最短 | 公开解 | 与公开解相同的非目标中间数 |','|---|---:|---:|---:|---:|---:|']
    for i in NAMES+sorted(set(rows)-set(NAMES)):
        r=rows[i];start=min(a['steps'] for a in first[i]['arms'].values())
        text.append(f"| {i} | {r['targets']} | {start} | {r['steps']} | {r['public']} | {r['overlap_helpers']}/{r['own_helpers']} |")
    text+=['','scored_0289 的 18 步解与公开程序没有相同的非初始、非目标中间数。我们的 154 同时用于得到 616、247 和目标 7,238，随后 616 可接到 615 和 2,465。scored_0810 的 29 步解中，265 的平方是 70,225，265 × 570 得到 151,050，而 570 的平方减去 38 又得到目标 324,862。','',
          '在 scored_0035 的首轮最短程序中，首次命中、命中第 15 个目标和覆盖全部目标分别在第 11、70 和 152 步。公开程序相应是 28、80 和 100 步。两个程序命中目标的顺序可以不同。','',
          '## 候选数诊断','',
          '固定第一轮的种子、构图器和 500 次预算。对三道历史难题，比较干净字典、在缺失值附近选取同等数量的随机对照数、加入全部缺失公开结果的数值。两个干预组均单独存档。后一组已看到公开解中的数值，未向搜索器提供寄存器程序或产生这些数的规则。','',
          '| 题号 | 首轮缺少的公开结果数 | 原字典 | 等量扰动数字 | 补入公开数值 | 公开解 |','|---|---:|---:|---:|---:|---:|']
    diag=read('diagnostic_public_value_intervention')
    for i,d in diag.items():
        best=lambda x:min(a['steps'] for a in x['arms'].values())
        for v in d.values():
            for a in v['arms'].values():assert validate(puzzles[i],a['program'])[0]==a['steps']
        text.append(f"| {i} | {len(first[i]['reference_missing'])}/{first[i]['reference_distinct']} | {best(first[i])} | {best(d['matched_noise'])} | {best(d['all_values'])} | {rows[i]['public']} |")
    text+=['','三道诊断题里，补齐公开结果意味着一个确实存在的短程序所需的数值全部在候选集中，全部合法的集内四则关系也已建图。此时仍然存在明显差距，表明即使数值覆盖充分，当前搜索也难以选出合适的整组依赖。该结论不依赖公开程序具有全局最优性。','',
           '## 复现与产物','',
           '第一轮默认运行 15 题。另 29 题通过同一脚本的 --ids 参数传入，题号见独立对照文件。--refine 读入前轮的自研程序以及同题已有的独立随机搜索结果。--catalog 增加反向检索的低成本算式，--marginal 在已计算数可复用的前提下重新估计下一个目标的增量成本。','',
           '    python3 experiments/benchmark_joint_bridges.py',
           '    python3 experiments/benchmark_joint_bridges.py --refine reports/joint_bridge_search.json --seed 35713 --trials 900 --output reports/joint_bridge_refinement.json',
           '    python3 experiments/diagnose_bridge_dictionary.py',
           '    python3 experiments/summarize_joint_bridge_search.py','',
           '逐题最短完整程序在 [已复核程序](joint_bridge_verified_programs.json)。固定预算数据在[首次实验](joint_bridge_search.json)和[后续整组对照](joint_bridge_holdout.json)。数值干预结果在[独立诊断文件](diagnostic_public_value_intervention.json)。','',
           '局部修复另测 8 道较短题，随机切断原图后让 CP-SAT 在小邻域内找严格改进，使用 OR-Tools 9.11.4210、每题 40 个邻域。直接删除旧中间数再按缺失的依赖寻找一个新值的试验使用每题 1,000 次提议。结果分别见 [CP-SAT 局部试验](joint_bridge_neighborhood.json)和[删点替换试验](joint_bridge_exchange.json)。']
    (REPORTS/'joint_bridge_study.md').write_text('\n'.join(text)+'\n')
    print('verified',tested,'programs;',len(rows),'cases;',wins,'wins;',ties,'ties')
    print('distribution',Counter(r['steps']-r['public'] for r in rows.values()))

if __name__=='__main__':main()
