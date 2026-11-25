# 算术图搜索实验

2026-11-25。在 1,000 道计分题中以固定种子 20261125 随机抽 12 题，另选 4 道历史讨论题。再以种子 20261126 从剩余题目抽 12 题。两组随机题和 4 道诊断题互不重叠。所有构造器只读取该题的初始数、目标、寄存器数和值域。公开程序只进入公开基线对照和独立的局部重写实验。

## 结果

| 方法 | 首批 12 题 | 第二批 12 题 | 24 题合计 |
|---|---:|---:|---:|
| 旧版 anchor 求解器 | 4,771 | 3,651 | 8,422 |
| 二阶字典和带符号进制起点 | 5,211 | 3,930 | 9,141 |
| 同时优化目标间差值和共享因子的算式图 | 5,026 | 3,795 | 8,821 |
| 从当前寄存器反向搜索乘积和余数 | 3,229 | 2,366 | 5,595 |
| 加入当前寄存器一步可造的数和乘积附近精确查差值 | 2,880 | 2,179 | 5,059 |
| 上一行加 9 次随机试算，轮流分配 | 2,814 | 2,130 | 4,944 |
| 上一行改为 UCB 分配，相同的 9 次试算 | 2,809 | 2,127 | 4,936 |
| 对多个独立构造结果逐题择优并重写依赖图 | 2,799 | 2,114 | 4,913 |
| 已存档公开基线，总分 132,255 的版本 | 1,834 | 1,353 | 3,187 |

## 搜索设置

- 浅层闭包完整保留初始值的零至二阶。当前寄存器的一阶临时扩展按不同数值去重，构造算式随数值保存。反向搜索每层只延伸评分最高的三个商和修正量组合，单条分支最多做四次商分解。
- 加减、乘法和整除遵守每道题的正整数值域。临时数按需写入寄存器。初始数固定保留，当前算式还会读取的值禁止覆盖，其余值按剩余目标的整除关系、小常数和共享因子等信息排序。
- 三个随机策略分别改变同量级目标的处理顺序、提高共享因子的评分、提高已能生成的修正量的评分。轮换和 UCB 均先各试一遍，随后再分配六次。UCB 用完整程序相对确定性解的步差映射为有界奖励，保留单题最佳。两个分配策略共用相同策略和试次对应的随机数，相同试算只执行一次。公平对比按每种分配策略请求的九次试算计。
- 局部重写先去除只服务一个结果的祖先，再让多个消费者共同更换共享中间数。恒等操作和去重按数值处理，候选程序重新分配寄存器并回放。公开程序单独接受同一类重写，28 题没有严格改善。
- 直接删去动态搜索中的目标两两 GCD 候选和对应保留偏好，24 题的确定性总步数从 5,059 变为 5,063。这项比较只衡量该求解器中显式 GCD 提示的边际收益。
- 结果是抽样实测。分阶段比较中，候选菜单、试算次数和总耗时会变化。UCB 和轮换的比较单独控制了试算次数。逐题完整指令、种子、操作次数或耗时见同目录 JSON。

## 复现

在项目根目录运行下列命令。测试通过后，两次基础实验生成两组结果，后两种搜索读取这两份结果，最后一条汇总独立构造与公开对照并输出最终指令。

```sh
python3 experiments/test_hybrid_graph_search.py
python3 experiments/benchmark_hybrid_graph.py
python3 experiments/benchmark_hybrid_graph.py --holdout
python3 experiments/benchmark_shared_repair.py reports/hybrid_graph_benchmark.json reports/hybrid_graph_holdout.json
python3 experiments/benchmark_rollout_bandit.py reports/hybrid_graph_benchmark.json reports/hybrid_graph_holdout.json
python3 experiments/finalize_hybrid_graph.py
```

单独测试具体题目可运行 `python3 experiments/benchmark_hybrid_graph.py --ids scored_0253 scored_0667`。基准测试读取已有的 `data/puzzles.csv` 与 `reports/baseline_lineage.sqlite`，和旧版对比还需要 `experiments/anchor_scored_submission.csv`。

## 算法来源

AlexDaPiggie 的实践提供了按需生成临时操作数、乘积逼近和按复用价值保留寄存器的思路。[策略记录](https://github.com/AlexDaPiggie/The_Elf_Calculator_Kaggle_Competition/blob/a7b8fa96d1ad4677d74934bc49eb5a84340d506a/STRATEGY.md)

niclox44 的实现提供了按构造成本选择共享因子、联合重写多个消费者的思路。本文对照的公开程序为该仓库存档的 public_v89，来源说明在仓库 README。[多因子构造器](https://github.com/niclox44/ElfCalculator-Kaggle/blob/f392d2444f5d87146a4a856f6f00a6cdc9c89c62/src/multifactor_solver.py) · [共享中间数的局部搜索](https://github.com/niclox44/ElfCalculator-Kaggle/blob/f392d2444f5d87146a4a856f6f00a6cdc9c89c62/native/elfopt_extended.cpp) · [基线说明](https://github.com/niclox44/ElfCalculator-Kaggle/blob/f392d2444f5d87146a4a856f6f00a6cdc9c89c62/README.md)
