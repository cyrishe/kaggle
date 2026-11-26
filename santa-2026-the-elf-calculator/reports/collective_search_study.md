# 因子、随机路径和公共计算图的联合实验

2026 年 11 月 26 日。在已有千题自研存档的基础上，本轮验证了 22 道不同计分题。所有计入成绩的程序均从题面或此前自研程序出发，逐条检查寄存器、整除、值域及目标覆盖。公开程序只用于比较步数。以公开代码从题面重建程序的对照单独记录。

| 样本及选择方法 | 道数 | 此前自研 | 本轮自研逐题最短 | 相同题目的存档公开参照 |
|---|---:|---:|---:|---:|
| 此前反复优化过的 0002、0060、0078、0529 | 4 | 1,049 | 895 | 715 |
| 从此前只存有基础解且至少 300 步的题中随机选 0074、0489 | 2 | 859 | 441 | 350 |
| 按题号选最大初值 ≤35、目标至少 26 个的 12 题，排除前述样本与 0006 | 12 | 3,862 | 2,110 | 1,487 |
| 另抽 100 题，在原抽样顺序中取最先触发自研结构检测的 3 题 | 3 | 1,237 | 612 | 486 |
| 公开仓库已展示的示例 0006 | 1 | 361 | 133 | 108 |

公开参照来自本地归档的 132,255 步版本。22 道中 21 道改善，1 道持平，6 道相对旧自研至少减半。旧存档合计 320,585 步，替换已验证的较短程序后得到 317,408 步。这一更新仅覆盖本轮测试题目。[可回放程序及出处](collective_search_best.json) · [逐题汇总脚本](../experiments/summarize_collective_search.py)

## 各组件贡献了什么

在六道核心对照题上，原始二阶有符号商搜索、加入有选择的三阶、再加入跨目标因子与修正量评分，各跑 32 次重启，分别为 1,538、1,487、1,446 步。以每题三种方法中最快做完 32 次的用时作为每题上限，截取已完成的尝试，对应 1,538、1,488、1,454 步。时间取本机并行任务的实测耗时。六题共用同一组题号和随机种子序列。[因子搜索代码与复现方法](collective_factor_study.md)

结构搜索由接近平方的目标提出可能的隐含操作数，再检验其他目标是否接近同一组数的乘积。对吻合的目标，同时安排操作数、乘积、尺度系数和修正量，并允许结果成为另一个目标的起点。这些数都用实际指令构造。另一条路径用蒙特卡洛重启改变开局和目标顺序，按量级抽三阶候选，用同余索引查询便宜的带符号修正量，再递归构造商。每条候选路径与其他路径的公共算式可以在整题重新选择。[结构搜索](../experiments/collective_factor_latent.py) · [随机路径实验](collective_walk_study.md)

12 道复核题中的 9 道触发结构搜索。通用搜索每题重启 48 次，触发题的专门路线另用 3–42 次代理题搜索。下表各行依次按题采用更短程序，同时比较单独做改图的收益。一次代理题搜索与一次原题搜索的用时可以不同。

| 复核组的程序来源 | 12 题步数 |
|---|---:|
| 通用搜索 | 2,459 |
| 通用搜索加随机改图 | 2,421 |
| 通用搜索加单层乘积表，两者逐题择短 | 2,346 |
| 再允许乘积和已得目标继续生成其他目标 | 2,141 |
| 在上一行逐题选中的单个程序上随机改图 | 2,112 |
| 两种程序同时提供候选算式，与前面程序逐题择短 | 2,110 |

更换构造路径贡献 318 步，其后再省 31 步。其中允许两个父程序同时提供算式多省 2 步。单独对通用搜索做改图能省 38 步。该组说明两类方法可叠加，部分收益发生在相同位置。相对强通用对照的净降幅为 14.2%。公开参照在这 12 题合计 1,487 步。[实际指令及单独、联合对照](collective_blind_joint_repair.json)

## 追加 512 次试算

另固定束宽 10，每道题完整运行一条包含 512 次重启的随机序列，记录截至各次数的最短整题。其余六题因子对照使用宽度 8。

| 题 | 1 次 | 32 次 | 128 次 | 256 次 | 512 次 | 全部自研路线最终择短 |
|---|---:|---:|---:|---:|---:|---:|
| 0002 | 311 | 311 | 311 | 310 | 310 | 308 |
| 0060 | 341 | 332 | 331 | 328 | 326 | 318 |

在另一条路径上，0060 的 8 个种子各走到首个目标，只让最短开局继续，10.4 秒得到 321 步。完整跑相同 8 个种子需 78.2 秒，也得到 321 步。对六题各自前三次完整轨迹进行回顾性检查，以首个目标步数筛选，六题合计 1,498；若事后从同三次中选全题最短，合计 1,486。早停可能错过更好的后段。[512 次完整轨迹](collective_factor_512_hard.json) · [六题首目标筛选复核](collective_prefix_check.json)

整图合并把不同自研程序中出现的算式并入同一个候选图，选择满足全部目标的无环子图，每个中间数在图中只计一次。最终重新分配 48 个寄存器，必要时重新生成被覆盖的中间数，按实际步数保留程序。六题首次合并中发现的一些收益也可仅由重排同一父程序得到。只有在重排后再缩短的分支，才能归因于跨程序选择。限定时长的约束搜索不提供整题最优证明。[整图选择与寄存器分配](../experiments/collective_extract.py) · [6 题回放](collective_fusion.json) · [2 道难题的最终合并](collective_fusion_hard.json)

## 结构出现的范围

排除以上六题、12 道复核题和 0006 后，以种子 119042 从另外 981 题等概率抽 100 题，自研算法给 46 题提出了结构候选。用最大初值 ≤35 且目标至少 26 个划分，组内 59 题触发 42 题，其余 41 题触发 4 题。逐题求解原抽样顺序中最先命中的 3 题，普通 48 次与结构法分别为 0203 的 286→267、0747 的 192→191、0715 的 207→154。触发是进一步搜索的理由，其收益须用完整程序计分。[抽样与结构筛选](collective_structure_screen.json) · [通用对照](collective_screen_control48.json) · [结构解](collective_screen_latent.json)

Hansen 的公开代码还可用三个乘积消去未知数。若三个目标分别接近 ab、ac、bc，便能从前两者的积除以第三者估计 a²，再以整数运算核验。外部检测器只读取题面，对 0529 找到 6 个数，可写出 26/30 个目标的带修正量乘积式。该外部检测配合本地表达式选择器，在 0529 和 0006 得到 157、130 步，单独保留。这一结果与自研筛查的参数、覆盖口径不同。[Hansen 的三角恢复源码](https://github.com/Hansen0223/Santa_2026/blob/3bfae157e32a3ea49d6333cf5b0619e9905d44e0/solvers/native/matrix_recover.cpp#L73-L108) · [外部假设与本地求解结果](collective_external_comparison.json)

## 复现

从竞赛目录运行，需自行准备官方 `data/puzzles.csv`。只核验本次选出的 22 份最短程序和千题总步数，用 Python 标准库即可。

```sh
python3 experiments/replay_collective_best.py
```

预期输出末行为 `replayed=22 archive_cases=1000 old=320585 saved=3177 updated=317408`。脚本对 22 题执行所有指令，另外 978 题沿用上次核验的逐题步数。[千题旧账本](saved_own_portfolio_audit.json) · [公开参照逐题步数](public_v89_step_counts.json)

如需复做基于外部检测器的对照，先运行 `python3.12 experiments/collective_matrix_fits.py`，再运行 `python3.12 experiments/collective_matrix_emit.py`。第一步下载并校验固定版本的源码，用本机编译器和官方题面还原输入。外部对照成绩保存在[单独的摘要](collective_external_comparison.json)。

六题与 12 题的 C++ 构造器、标准参数和固定种子见[因子实验说明](collective_factor_study.md)与[随机路径说明](collective_walk_study.md)。下列命令补充复现追加预算、早期结构筛查和最终计分。整图抽取使用 OR-Tools 9.11，机器负载会影响限定秒数内取得的结果。已保存的选定程序可以直接回放。

```sh
python3.12 experiments/collective_factor_bench.py --ids 2 60 --modes 2 --trials 512 --width 10 --workers 2 --out reports/collective_factor_512_hard.json
python3.12 experiments/collective_blind_joint_repair.py
python3.12 experiments/collective_structure_screen.py
python3.12 experiments/collective_factor_latent.py --ids 203 747 715 --out reports/collective_screen_latent.json
python3.12 experiments/collective_factor_bench.py --ids 203 747 715 --modes 2 --trials 48 --width 8 --out reports/collective_screen_control48.json
python experiments/collective_extract.py --donors collective_factor_32.json --donors collective_factor_latent.json --donors collective_walk.json --donors collective_walk_modular.json --donors collective_walk_ladder.json --donors collective_walk_meet.json --seconds 12 --output reports/collective_fusion.json
python experiments/collective_extract.py --donors collective_factor_32.json --donors collective_factor_latent.json --donors collective_walk.json --donors collective_walk_modular.json --donors collective_walk_ladder.json --donors collective_walk_meet.json --seconds 12 --extra-arcs 3 --output reports/collective_fusion_extra.json
python experiments/collective_extract.py --ids scored_0002 scored_0060 --donors collective_fusion.json --donors collective_factor_512_hard.json --donors collective_walk_prefix_race.json --donors collective_walk_0060_restarts.json --donors collective_factor_32.json --seconds 15 --output reports/collective_fusion_hard.json
python3.12 experiments/summarize_collective_search.py
```
