# Santa 2026 — The Elf Calculator

Kaggle 竞赛的调研、数据分析和求解实验。目标是为 1,000 道题编写算术程序，使每题给定的目标值至少出现一次，并最小化总指令数。计算器有 48 个寄存器，运算要求正整数、精确除法和题目规定的数值上限。[竞赛页面](https://www.kaggle.com/competitions/santa-2026/overview)

研究结论、实验分数、来源与局限见 [PROGRESS.md](PROGRESS.md)。当前文件保留了实验代码和汇总结果，其中 `scored_0810` 的 34 步解是单题手工构造，并非已泛化的自动解法。

## 换环境继续研究

从 [2026-11-25 交接说明](HANDOFF.md) 开始，可复核 44 题的自研程序、重建公开基线血缘库，并运行一次新的搜索。[最新逐题实验和诊断](reports/joint_bridge_study.md)记录了 326 份独立候选的复核结果。

## 准备数据

从 Kaggle 竞赛 Data 页面获取数据并遵守竞赛规则，或在已配置 Kaggle CLI、登录并接受竞赛规则后，在本目录运行：

```bash
mkdir -p data
kaggle competitions download -c santa-2026 -p data
unzip data/santa-2026.zip -d data
```

需要 `data/puzzles.csv`、`data/practice_puzzles.csv` 和 `data/sample_submission.csv`。仓库不包含竞赛原始数据。本地从 Kaggle 下载的官方 CSV 使用 CRLF 换行；将换行规范化为 LF 后，SHA-256 与此前记录的公开镜像一致：

```text
puzzles.csv            41ae9beee69a49778a549012a14d2010e7c9d9af36997f1b84a4a8ad4222ad85
practice_puzzles.csv   13934566fc50cc25b2178d7a35287864127881e0f848f4a4e7b799089e7510bf
sample_submission.csv  8d9e65baff997d5faa15cb654546a296457650436603928de0b07413cfa7e559
```

## 运行实验

Python 标准库即可运行以下脚本。在本目录执行：

```bash
python3 experiments/analyze_puzzle_distributions.py
python3 experiments/first_solver.py --id scored_0001
python3 experiments/small_state_search.py --id practice_0039
python3 experiments/discover_patterns.py scored_0810 scored_0596
python3 experiments/shared_factor_case.py
```

注意多个脚本会覆盖 `experiments/` 里的同名输出文件。首次全量生成第一版及锚点版需要：

```bash
python3 experiments/evaluate_all.py --sample 1000
python3 experiments/evaluate_anchor_scored.py
```

这会分别生成本地忽略的 `experiments/full_programs.csv` 和 `experiments/anchor_scored_submission.csv`，供部分后续脚本读取。全量搜索耗时取决于机器，历史一次运行约 10 分钟。结果可能因代码后来调整而与旧报告不同，须以本地验证为准。

`recursive_window_experiment.py` 需要本地生成或提供 `experiments/deep_ten_best.csv`（十道题的逐题较优解），该程序文件未纳入仓库。`deep_ten.py` 则需要先生成 `experiments/anchor_scored_submission.csv`。每个程序应经过 `experiments/first_solver.py` 中的 `validate` 逐题回放；这不是 Kaggle 官方评测。

## 第三方公开 baseline

本地分析曾使用 [Hansen0223/Santa_2026 固定提交版本](https://github.com/Hansen0223/Santa_2026/tree/0652a700782bf452d35255b9b4993f547412cfcc)，源文件 `submission.csv` 的 SHA-256：

```text
0f27cc12b9c6a59e7a61f2eaea9749e68b6d73601c599d8199d2db0761a57204
```

该文件 1,000 行本地回放为 139,406 步，来自第三方，不能称作本项目原创。复现公开 baseline 的 30 题分析时，将该固定版本的 `submission.csv` 放在 `external/hansen_0652a700/submission.csv`，然后运行：

```bash
python3 experiments/review_public_baseline.py
python3 experiments/review_initial_final_30.py
```

原仓库说明其多个求解器和候选含其他作者贡献，代码使用和再分发前请检查各文件来源与许可；[来源及许可证记录](https://github.com/Hansen0223/Santa_2026/blob/0652a700782bf452d35255b9b4993f547412cfcc/generative/NOTICE.md)。该第三方完整提交不包含在本仓库。

## 近期研究与复现

- [开源基线调研](OPEN_SOURCE_RESEARCH.md)、[优化试验](OPTIMIZATION_RESEARCH.md)
- [因子研究](FACTOR_RESEARCH.md)、[共享复合因子](FACTOR_SHARED_STUDY.md)
- [20 题公因数抽样](GCD_SAMPLE_STUDY.md)、[50 题初值分析](INITIAL_GCD_50_STUDY.md)
- [乘积锚点分析](PRODUCT_ANCHOR_STUDY.md)、[多路径搜索](DIVERSE_PRODUCT_BEAM_STUDY.md)
- [不含原始题目及完整候选程序的实验汇总](experiments/research_summary.json)

为遵守“数据不入库”，`data/`、`external/`、包含逐题原始数值或完整第三方程序的详细轨迹及 `experiments/pilot_*/` 均被忽略；研究文档中提到的本地详细结果需要运行对应脚本自行生成。复现多路径等图实验需要 Python 3.12+ 和固定版本第三方仓库，素因子分析另需 SymPy。第三方代码及程序不包含在本仓库，并须遵循各自来源和许可。

```bash
git clone https://github.com/Hansen0223/Santa_2026.git external/hansen_repository
git -C external/hansen_repository checkout 0652a700782bf452d35255b9b4993f547412cfcc
# 从 Asterios 公开数据集 v196 获取 best_programs.csv 到 external/asterios_v196/
python3 experiments/merge_public.py external/asterios_v196/best_programs.csv external/hansen_repository/public-assisted/submission.csv external/hansen_repository/submission.csv --output external/asterios_v196/merged_132477.csv
python3.13 tests/test_factor_joint.py
python3.13 tests/test_diverse_product_beam.py
```

[Asterios v196 公开数据集](https://www.kaggle.com/datasets/asteriospanoras/santa-2026-elf-programs-and-experiments/versions/196)的程序来自多个贡献者；逐题署名和许可证需随来源保留。132,477 是多份公开程序逐题择短的本地回放结果，不能归为本项目原创，亦不代表 Kaggle 官方成绩。
