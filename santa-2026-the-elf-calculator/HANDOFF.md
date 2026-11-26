# 换环境继续 Elf Calculator 研究

## 2026-11-26 的搜索实验与回放

从本竞赛目录运行以下命令。回放仅需 Python 标准库和官方文件 `data/puzzles.csv`。

```sh
python3 experiments/replay_collective_best.py
```

22 份程序的指令回放和千题旧步数复算通过后，最后一行应为 `replayed=22 archive_cases=1000 old=320585 saved=3177 updated=317408`。要从本轮各组候选重新选出逐题最短程序，运行 `python3.12 experiments/summarize_collective_search.py`，将复核 280 份候选记录，其中有重复的程序。[逐题程序](reports/collective_search_best.json) · [实验设计与重跑命令](reports/collective_search_study.md)

## 2026-11-25 的实验归档

更新于 2026-11-25。最新一轮有 44 道计分题的完整自研程序，合计 2,786 步。同题的公开存档合计 2,090 步。三题持平，分别是 scored_0289（18 步）、scored_0399（21 步）和 scored_0810（29 步）。这批题包括按最大目标值选出的组和历史诊断题。各轮对部分题追加了搜索，不能用这个合计推算千题成绩。[44 题逐题结果与固定预算对照](reports/joint_bridge_study.md)

## 在新机器回放已有结果

以下命令从仓库的 `santa-2026-the-elf-calculator/` 目录运行。已用 Python 3.12 在 macOS 上验证。回放只用 Python 标准库。先按 [README 的数据准备说明](README.md#准备数据) 下载官方文件，单独回放仅需 `data/puzzles.csv`。

```sh
python3 experiments/replay_saved_programs.py
python3 experiments/replay_saved_programs.py scored_0289 scored_0399 scored_0810
```

第一条应输出 `cases=44  own=2786  archived_public=2090  wins=0  ties=3`。程序逐条执行每个自研解，检查值域、寄存器、整除、目标覆盖和程序长度。输出中的公开步数来自已归档的比较结果。[44 份完整自研程序](reports/joint_bridge_verified_programs.json)

## 重建公开程序的血缘数据库

最新对照固定为 niclox44 仓库的 public_v89。为避免结果跨版本漂移，使用以下提交和文件。早期报告还分别比较过 139,406 与 132,477 步的其他存档。[来源与作者说明](https://github.com/niclox44/ElfCalculator-Kaggle/blob/f392d2444f5d87146a4a856f6f00a6cdc9c89c62/README.md)

```sh
mkdir -p external reports
curl -fL --retry 3 -o external/submission_public_v89.csv https://raw.githubusercontent.com/niclox44/ElfCalculator-Kaggle/f392d2444f5d87146a4a856f6f00a6cdc9c89c62/submissions/submission_public_v89.csv
python3 -c "import hashlib, pathlib; p=pathlib.Path('external/submission_public_v89.csv'); assert hashlib.sha256(p.read_bytes()).hexdigest() == '4590f6fa27c902762f03ddb2af6c4dfc103ae44fe65ae02d4937eea1e0e6eb14'"
python3 experiments/baseline_lineage.py build external/submission_public_v89.csv
python3 experiments/summarize_joint_bridge_search.py
```

最后一条将重新回放 326 个独立候选、核对公开程序并重建 44 题报告，预期为 0 题胜出、3 题持平。数据库可用 `python3 experiments/baseline_lineage.py trace scored_0810 --step 10` 检查指定步骤的祖先。下载数据、公开提交与重建的 SQLite 留在机器本地。

## 重新跑一次独立搜索

需要命令 `c++` 可用且支持 C++17，脚本在临时目录编译搜索器。以下命令以单题验证从题面生成、48 个寄存器调度和公开对照的全流程。输出单独写入本地目录，归档结果仍可用于比较。相同种子在不同 C++ 标准库上的随机采样顺序可能有差异。

```sh
mkdir -p local-runs
python3 experiments/benchmark_joint_bridges.py --ids scored_0289 --seed 20261125 --trials 500 --workers 1 --output local-runs/scored_0289.json
```

Python 入口负责候选构造、排程和回放，C++ 搜索器负责选择及删减一整组中间数。[候选构造与运行入口](experiments/benchmark_joint_bridges.py) · [C++ 搜索器](experiments/joint_bridge_search.cpp)

只有 CP-SAT 局部搜索实验用到 OR-Tools，原实验使用 `ortools==9.11.4210`。用 `python3 -m venv .venv` 建立环境后，可用 `.venv/bin/python -m pip install ortools==9.11.4210` 安装。比较更早的锚点方法时，还需要按 README 生成本地的旧版候选。

## 值得延续的结论

| 待解决的问题 | 已有证据 |
|---|---|
| 应该在哪一层引入随机性 | 44 题各 500 次候选提议。仅随机改算式价格，合计仍为 2,924 步。引入成组中间数和供体子图，再联合删减为 2,835 步。按可服务结果数加权为 2,834 步。[实验](reports/joint_bridge_study.md) |
| 好的局部状态能否继续优化 | scored_0035 从精英路径中段续算 200 次，159 次完成；同预算独立重开完成 23 次，最短分别为 140 和 144 步。scored_0667 的 500 次独立尝试均未在 150 步内完成。[随机探索报告](reports/monte_carlo_500_study.md) |
| 哪些题适合先求共同因子 | 49 道强共同因子题中，先求商并与直接求解逐题择优，从 4,977 步降至 4,855 步，30 题改善。[共同因子实验](reports/factor_routing_study.md) |
| 候选数全了能否直接找到短解 | 对 scored_0667 单独注入全部缺失的公开结果值，241 → 234，公开为 117。三道诊断题中另两题没有改善；这些诊断结果单独保存。[数值干预实验](reports/joint_bridge_study.md#候选数诊断) |

血缘统计保留了 1,000 题的首次目标最大阶、四则运算随相对阶的分布，以及中间数被不同目标继承的比例。200 / 400 次开局实验和两批各 12 题的混合搜索也有独立记录。[逐题阶数](reports/baseline_forward_depth_by_puzzle.csv) · [相对阶与运算](reports/relative_depth_operations.json) · [复用统计](reports/lineage_and_search_summary.json) · [开局实验](reports/opening_walk_summary.json) · [混合搜索](reports/hybrid_graph_experiment.md)

## 下一个待验证的实验

对同一批开局各做多次不同目标顺序的贪心续算，用最终覆盖整题的成本为开局排序。保留早期命中较慢、但后期能复用中间数的路径。动机来自 scored_0035 的首轮程序，第 15 个目标到全部完成用了 82 步，公开解在这个区间只用 20 步，两边的目标顺序可以不同。这个开局评分方法尚未测试。

先在 scored_0035、scored_0253、scored_0667 对照相同续算总预算下的独立重启与多次续算，再用未参与调参的题复测。保留随机种子、完整解比例、最短合法程序与耗时；达到步数上限的部分路径只计命中数。
