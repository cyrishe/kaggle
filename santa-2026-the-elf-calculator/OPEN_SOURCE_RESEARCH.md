# 开源求解器与图优化调研

调研对象：Hansen0223/Santa_2026 固定提交 `0652a700782bf452d35255b9b4993f547412cfcc`，不是我们自己的代码。来源与每个文件的许可证见 [generative/NOTICE](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/generative/NOTICE.md) 和 [public-assisted/NOTICE](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/public-assisted/NOTICE.md)。此处的实验成绩是该固定版本记录的历史本地成绩，不代表当前榜单。

## 官方数据与本地复核

2026-11-23 从 Kaggle Data 页面下载 `santa-2026.zip`，解压到忽略版本控制的 `data/`。原始三个文件为 CRLF，`puzzles.csv` 的原始 SHA-256 为 `b0c70d849eca078a0e1cf9a4f7b47fd40b7435663f6f84de6725f84724500428`。将 CRLF 换成 LF 后，三个文件的 SHA-256 均与项目 README 先前记录的镜像哈希一致；本项目未更改原文件。

用本项目 `experiments/first_solver.py` 的解释器对固定版本的 `submission.csv` 和 `public-assisted/submission.csv` 逐题回放：分别是 1000 题、139406 步和 1000 题、133611 步。前者文件 SHA-256 为 `0f27cc12b9c6a59e7a61f2eaea9749e68b6d73601c599d8199d2db0761a57204`。本地回放不等于 Kaggle 提交。原仓库 README 的独立程序总数 139429 与实际文件有差异，以本次重放为准。原仓库另记录 132477 步的组合候选，需要额外公开档案重建，我们没有下载或验证它。

运行仓库 `collaboration/exact-boundary/verify.py` 时使用官方原始 CSV，结果为 `scored_0649` 的完整程序 119 → 118 步，固定的 25 个出口子图 29 → 28 步，其余 90 条算式相同。该命令只验证给出的见证；没有运行原生精确搜索，因此没有独立复核其最短性证明。

## 图方法到底做了什么

- **单图局部重建**：`solvers/graphs/virtual_cuts.py` 选共享辅助值及其使用者，找出区域出口、其余目标仍需的依赖和可用输入，把多个出口交给搜索器重新构造。候选必须经过整图依赖裁剪与寄存器编译，且实体程序更短才保留。
- **多个父本的算式库 + CP-SAT**：`generative/component_select.py` 从多个程序提取整数和候选运算；固定拓扑顺序，找必须存在的值，将余下约束分成独立块，选择最少辅助值；然后还要实际分配寄存器并回放。最优只针对候选库、所试顺序和求解状态，不是全题最优。
- **最小割组合父本**：`collaboration/recipe-union/cut_parents.py` 对共同边界值选择左或右父本的私有计算路径；共享的私有中间值只记一次，构成最小割，约束边界依赖顺序，再落地并搜索。最优只针对固定两份父本、边界和顺序。历史实验独立组 614 题，混合起点和直接搜索逐题取短，9 题共省 10 步，其中 3 题混合起点优于对照；160 道公开组合题无缩短。[实验说明](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/collaboration/recipe-union/README.md)
- **精确重建共同出口**：0649 给出了特别接近我们想法的案例。旧辅助数 7、23、64、361 改成 64、363、7428，25 个出口保留，整题省 1 步。作者记录在固定边界及搜索模型下排除更少辅助数；不能把固定边界最优解释为整题最优。[完整案例](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/collaboration/exact-boundary/README.md)
- **寄存器和重计算**：纯值图更小并不一定能排进 48 个寄存器，偶尔保留重复计算反而有益；`collaboration/register-search/README.md` 记录 0493 只折叠部分重复计算的实例。可用旧图作为约束或回退，并以真实指令数为准。

## 有效和无效的实验需要一起看

原作者历史固定父本上，GoodPJW DAG 搜索使独立路线 218 题省 329 步、公开辅助路线 42 题省 55 步；Arsen 候选选择及共享辅助值排序也分别省 58 和 23 步。它们对应各自不同父本，不能相加成同一次提升。[方法表](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/collaboration/methods.md)

局部多出口共享的一个实验在 96 道独立题及 64 道组合题检查 27677 个切口、没有找到严格缩短；多父本局部重建也有无收益实验。相反，对较大中段重新搜索，独立组 896 题经对照择短省 25 步；组合组 887 题有 3 题由中段重写各省 1 步。这些是各自实验条件下的结果，不是方法普遍无效或有效的保证。[局部电路](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/collaboration/circuit-cuts/README.md) · [中段搜索](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/collaboration/register-search/README.md)

## 对我们下一轮的建议

1. 以实际官方目标标记输出，保留两套不同父本和每题来源；先复现 0649 见证作为图重建回归样例。
2. 利用真实目标找高扇出节点、可移除独占分支和多个出口，构造固定边界子问题；允许搜索新的共享值，而非只在旧值之间做一步替换。
3. 每题给相同预算的直接搜索、局部重建和多父本混合做配对对照；记录新增候选、理论图节点数、寄存器编译后的指令数及耗时。历史强公开解收益很小，优先小样本核验。
4. 候选选择优化把“重建共享值的成本”和“被多个出口重复使用的成本”合并计算，同时检查循环、整数合法性和 48 寄存器；选择后进行完整回放，失败则回退原程序。
