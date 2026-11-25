import json
from pathlib import Path
from collections import Counter
from statistics import median
R=Path('reports')
read=lambda n:json.loads((R/n).read_text())
features=read('factor_routing.json')
f=features['cases'];b=read('factor_routing_benchmark.json');q=read('factor_quotient_programs.json');l=read('factor_routing_lineage.json')
assert all('order_control' in v for v in q.values())
lines=['# 按目标共同因子选择解法','',
'2026-11-25。本地使用全部 1,000 道计分题及存档的 132,255 步公开程序。题面分组只读取初始数、目标和值域。','',
'## 分组','',
'同一因子须至少为 100 且严格大于最大初始数。精确整除至少 3 个目标，每个商至少为 2。通过枚举每对目标最大公约数的全部约数计数。','',
'| 最低覆盖比例 | 因子至少为 100 的题数 | 因子至少为 1,000 的题数 |','|---|---:|---:|']
for den,percent in [(10,'10%'),(5,'20%'),(4,'25%'),(3,'1/3')]:
    counts=[sum(p['best_exact_by_size'][str(c)]>=max(3,(p['n']+den-1)//den) for p in f.values()) for c in [100,1000]]
    lines.append(f'| {percent} | {counts[0]} | {counts[1]} |')
lines+=['','为每题生成 5 组对照，每个目标在原值上下 1% 内随机扰动，扰动半径另受相邻目标距离的四分之一及值域限制。因子至少为 100 时，5,000 组对照中 1 组通过 20% 门槛，269 组通过 10% 门槛。该对照保留量级和局部间距，未刻意保留奇偶性。','',
'分类时先判断 20% 的精确共同因子，再判断共同非零余数，再判断目标之间的便宜差值或倍数加减，最后判断 10% 的精确共同因子。共同余数至少覆盖 4 个且达到全题 20%。对目标之间的关系，按有至少一个更小来源目标的不同终点计数；乘数和修正量分别可从初始数用至多两条指令构造。差值与倍数加减取覆盖终点较多的一类，同数时优先差值。','',
'| 依次归入的类别 | 题数 |','|---|---:|']
labels={'factor':'强共同因子','residue':'共同非零余数','affine':'目标倍数加减','delta':'目标加减','weak_factor':'较弱共同因子','general':'其余'}
for name,label in labels.items():
    lines.append(f"| {label} | {sum(v['route']==name for v in f.values())} |")
lines+=['','## 商空间构造','',
'对一组精确整除的目标，同时求出因子、该组的全部商以及未入组的原目标。将乘回因子的指令并入依赖图，尝试提前产出已备齐操作数的目标，重新分配 48 个寄存器，回放完整原题。候选包括按覆盖数量排序的至多三种不同目标子集，以及一种覆盖最广、优先低阶可造的备选因子。','',
'直接求解的对照使用同一个通用求解器，尝试原目标顺序、组内目标优先，并以块内乱序补足到商空间试算次数；按题保留最短合法程序。以下对照还与固定顺序的通用基线取短。两侧控制构造尝试次数，单次耗时可能不同。','',
'| 类别 | 实测题数 | 直接求解 | 只用商空间 | 两者逐题取短 | 商空间严格改进题数 | 公开解步数 |','|---|---:|---:|---:|---:|---:|---:|']
for t in ('factor','weak_factor'):
    group={i:x for i,x in q.items() if f[i]['route']==t}
    pairs=[(min(x['control'],b[i]['live']['control']),x['steps']) for i,x in group.items()]
    public=sum(b[i]['public']['control'] for i in group)
    lines.append(f'| {labels[t]} | {len(pairs)} | {sum(c for c,v in pairs):,} | {sum(v for c,v in pairs):,} | {sum(min(c,v) for c,v in pairs):,} | {sum(v<c for c,v in pairs)} | {public:,} |')
lines+=['','强因子组全部测试，较弱组固定种子分层抽样。逐题程序和所有尝试步数见 [商空间构造结果](factor_quotient_programs.json)。','',
'## 重写已有图','',
'保留已有程序作候选，先按原产生顺序及依赖图顺序做去重和寄存器调度，再比较各类替换的增量。以下列出确定性通用解的结果。','',
'| 归入的类别 | 测试题数 | 实施策略 | 原步数 | 优化后 | 改进题数 |','|---|---:|---|---:|---:|---:|']
for name in labels:
    sel=[r['live'] for r in b.values() if r['route']==name]
    key='factor' if name=='weak_factor' else name
    vals=[min(x[k]['steps'] for k in ('factor','residue','affine','delta')) if key=='general' else x[key]['steps'] for x in sel]
    lines.append(f"| {labels[name]} | {len(sel)} | {labels[key] if key not in ('factor','general') else ('因子及其乘积重写' if key=='factor' else '逐题取短')} | {sum(x['control'] for x in sel):,} | {sum(vals):,} | {sum(v<x['control'] for x,v in zip(sel,vals))} |")
lines+=['','在 49 道强因子题中，用相同方法重写旧版锚点程序，8,270 步降到 7,736 步。重写存档公开程序仍为 3,385 步。119 道重写测试中，所有受测策略均未缩短对应公开程序。','',
'逐题数据见 [分类](factor_routing.json)、[图重写及胜出程序](factor_routing_benchmark.json)、[公开程序血缘核对](factor_routing_lineage.json)。公开程序中，49 道强因子题有 29 道至少一个筛出的因子作为乘法输入影响一个被它整除的目标，有 20 道存在一个筛出的因子通过乘法影响其整除组全部成员。','',
'在 scored_0307，166 整除 9 个目标，1,328 整除 6 个。公开解第 10 步计算 1,328 × 2 = 2,656，全部 28 个目标都继承了这个结果。在 scored_0755，目标 3,869,934,195 乘以 12 再加 2、乘以 20 再减 17，可以直接得到两个别的目标。目标间倍数加减重写使通用解从 195 步降至 187 步。','',
'## 复现','',
'在项目根目录运行以下命令。','',
'```sh','python3 experiments/factor_routing.py','python3 experiments/check_factor_routing_lineage.py','python3 experiments/benchmark_factor_routing.py','python3 experiments/factor_quotient_solver.py','```']
(R/'factor_routing_study.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines[30:43]))
