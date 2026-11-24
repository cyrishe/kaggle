# 竞赛优化试验记录

## 数据、来源及评价

官方数据保存在忽略版本控制的 `data/`；题目文件原始 SHA-256 为 `b0c70d849eca078a0e1cf9a4f7b47fd40b7435663f6f84de6725f84724500428`。比赛为 1000 题总步数，无公开/私有榜切分；每条指令都计费，非法程序或漏目标会导致提交无效。以下都是本地回放，不是官方提交成绩。

Asterios Panoras 固定 [v196 数据集](https://www.kaggle.com/datasets/asteriospanoras/santa-2026-elf-programs-and-experiments/versions/196) 归档 SHA-256 `71d54c19f6e8d8f0b0b855b5e7f9280946b46c8b3db83beebcf0ddcbed097cc5`，其中 `best_programs.csv` 的 SHA-256 `cf4a0065ff5f2aa7b70734cb1ac36c49539c8213abc2593f6e816b674f328aea`。该版本由多位作者的公开程序组合构成，须保留它的 `source` 及各原始许可证；该数据集页面标注 Apache 2.0。

通过本项目解释器，v196 完整回放为 132584 步。在每题择取 v196、Hansen0223 固定提交 `0652a700782bf452d35255b9b4993f547412cfcc` 的公开辅助文件和独立文件中更短的合法程序，得到 **132477 步**。两套本地解释器均已回放全部 1000 题。组合相对 v196 15 题共省 107 步；它是已公开结果的组合，不是新的求解算法。文件为 `external/asterios_v196/merged_132477.csv`，SHA-256 `18ce30650bfbdd16e392aa406a1522746179c8194585593443d93f0c59cbd950`。其总步数与原仓库记录的 132477 相同，但文件哈希不同，不声称两个提交逐题或逐指令相同。

复现（`HANSEN` 为该固定版本仓库路径）：

```sh
python3 experiments/merge_public.py external/asterios_v196/best_programs.csv "$HANSEN/public-assisted/submission.csv" "$HANSEN/submission.csv" --output external/asterios_v196/merged_reproduced.csv
```

逐题来源生成于同名 `.origins.json`；对仓库两份输入仍需结合各自 `origins.csv` 和 NOTICE 追溯具体作者。数据与第三方完整程序均位于 Git 忽略目录。距离用户给出的历史 126000 步参考为 6477 步；这是差距计算，不是实时榜单核实。

## 数论 + 图的自主原型：共享桥接数

`experiments/shared_bridge_pilot.py` 对两个或更多目标的值逆推：寻找新的整数 H，使目标可由 H 和原图中较早产生的数经一步四则运算得到；H 自身需由原图中更早的两个值一步算出。将多个目标的算式同时替换，重新计算目标依赖闭包，然后用固定版本开源图编译器分配寄存器并回放完整程序。新代码是有界启发式：仅考虑目标节点、单个新辅助数、一步构造和既定顺序，每个 H 最多采用首个符合条件的构造；最多对每个 H 的前 8 个出口枚举两两替换，不是穷尽搜索。

人工例初值 `[2,3,7]`，目标 `[13,17]`，原程序分别经 `2*7=14, 14+3=17` 和 `2*3=6, 7+6=13`，共 4 步；算法找出共享值 `3+7=10`，再得到 `10+3=13` 和 `10+7=17`，共 3 步，实体程序回放通过。真实数据选取 20 道固定题测试，使用 v196 作为父程序：没有图节点节省，也没有实体程序收益；实验结果见 `experiments/pilot_bridge_v196_20/report.json`。样本不是随机估计，结果只适用于这批题和搜索范围。

## 可继续尝试的算法方向

1. **数论候选生成**：针对一个局部出口组，枚举最大公因子、近似公共乘数、共享商余数和近平方；按真实构造代价，而不是关系式漂亮程度排序。严格限制中间值与精确除法，并考虑同一辅助数为多个出口分摊的边际成本。
2. **图选区与联立重建**：按多出口共享依赖、节点排他性和可删子图规模选局部区域，允许 2–3 个新增辅助数；候选要保留图外用到的边界。采用有向超图/约束选择或小域精确搜索，最小割适合双父本固定边界选择，不能当成全局最优证明。
3. **贪心应算整图增量**：为每个候选计算新增依赖并集减去可移除的旧依赖并集；对多个出口重复计算只计一次。保留多个多样化候选，允许短暂等长或更长，之后用图搜索继续探索；严格缩短才写入最后结果。
4. **检索与预算**：离线建立候选算式索引，以数值、因数、余数和已有祖先集合检索；用近似代价或上下界筛选，在高潜力题上分配较多预算。必须与同样轮数、种子和父本的直接搜索对照。
5. **实体编译与验证**：所有候选重新分配 48 个寄存器，允许必要时重算；仅采用真实程序较短且完整回放通过者。区分搜索超时、未找到和已证明最优，保留每题的来源、随机种子、编译器版本、成本和时间。

已公开的 [v196 实验表](https://www.kaggle.com/datasets/asteriospanoras/santa-2026-elf-programs-and-experiments/versions/196) 曾观察到：局部目标的叶子可能在不同时间被覆盖，所以“某个时间点找不到短表达式”不是全局无解证明。简单独立求解目标忽略共享，也容易重复计费。更深入的原仓库代码和成功/失败对照见 `OPEN_SOURCE_RESEARCH.md`。

## 图检索的配对试验

编译固定仓库的 Wang Jakie `generative/wang/anneal_seeded.cpp`（Apache 2.0，来源与改动见该目录的 NOTICE），使用 `experiments/portfolio_pilot.py` 做等随机种子和等轮数的单父本/双父本比较；每组搜索都从公开辅助程序出发，双父本另外提供独立程序。按公开辅助程序长度分层，固定随机种子 `20261123` 选 48 题，每组每题 600 轮；执行结果完整保存在 `experiments/pilot_48/report.json`。

单父本 48 题省 0 步，双父本在 `scored_0962` 从 31 降到 30 步，其第二父本是 33 步，整表从 133611 降到 133610；候选已按官方数据全表回放。**但 v196 同题已经有 30 步**，因此这个结果对 132477 组合的净改进为 0。它说明搜索能重构出不同或更短的路径，但不能把该历史起点的提升误称为最新基线收益，也不足以判定双父本普遍有效。

用强组合为父本、独立程序为第二父本，进行另一批等预算小样本；具体结果以 `experiments/pilot_132477_16/report.json` 为准。源程序版权、逐题上游来源见仓库 `generative/wang/NOTICE.md`、`public-assisted/NOTICE.md` 和 `origins.csv`。运行的 `g++` 为 Apple clang 17.0.0，编译参数 `-O3 -std=c++20`；随机搜索不保证跨平台完全一致。

强组合的配对试验现已完成：以 132477 组合为父本、独立程序为第二父本，按父本长度分层固定种子抽 16 题，每个方向每题 400 轮。单父本和双父本均无严格缩短，全表仍为 132477，均经官方题目完整回放。抽样规模小、预算有限，不能推断其他题或更大预算的结果。

另一组对 v196 抽 24 题、每方向 400 轮：单父本无收益；双父本将 `scored_0803` 从 128 变为 119，整表从 132584 变 132575。119 步与提供的第二父本相同，并已在 132477 组合中，因此不是新的净收益。

在项目目录的可复现示例（此前已从上游源码构建 `/tmp/santa_graph_bin/anneal_seeded`，可将其换为本机二进制目录）：

```sh
g++ -O3 -std=c++20 external/hansen_repository/generative/wang/anneal_seeded.cpp -o /tmp/santa_graph_bin/anneal_seeded
python3 experiments/portfolio_pilot.py --baseline external/asterios_v196/merged_132477.csv --donor external/hansen_repository/submission.csv --bin-dir /tmp/santa_graph_bin --sample 16 --rounds 400 --jobs 2 --out experiments/pilot_132477_16
/opt/homebrew/bin/python3.13 experiments/shared_bridge_pilot.py --repo external/hansen_repository --baseline external/asterios_v196/submission.csv --ids scored_0810 scored_0962 scored_0649 scored_0134 --out experiments/pilot_bridge --max-helpers 300
```

真实题集上的共享桥接试验是 v196，不是上述 132477 组合；它们有不同来源，不混同结论。公开优化器和图编译器均不归本项目作者所有。
