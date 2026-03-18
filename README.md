# Signed Circular Edge Coloring

**符号图圆环边染色计算 / Exact computation for signed-graph circular edge coloring**

本项目面向符号图的圆环边染色色数计算，研究在给定底图 `(G, σ)` 的条件下，如何精确判定某个圆环周长 `r` 是否可行，并进一步求出最小可行圆环周长。仓库当前提供三个核心能力：`decide` 用于固定 `r` 的可染性判定，`optimize` 用于最小 `r` 求解，`verify` 用于对求解得到的颜色证据做独立校验。

This repository studies circular edge coloring for signed graphs. Given a concrete instance `(G, σ)`, it supports feasibility checking for a fixed circumference `r`, exact optimization of the minimum feasible circumference, and independent verification of the returned witness.

## Quick Start / 快速开始

Recommended order: install dependencies -> run one instance -> inspect files under `artifacts/runs/`.

推荐使用顺序：安装依赖 -> 运行一个实例 -> 查看 `artifacts/runs/` 中的结果文件。

### 1. Install dependencies / 安装依赖

```powershell
python -m pip install -e .[dev]
```

### 2. Decide whether a fixed `r` is feasible / 固定 `r` 判定是否可染

Use `decide` when you already have a candidate circumference and only need a yes/no answer plus a witness when feasible.

当你已经有候选圆环周长 `r`，只需要判断它是否可行时，使用 `decide`。

```powershell
python -m signedcoloring decide --instance data/instances/star_k1_3_positive.json --r 3
```

### 3. Optimize the minimum feasible circumference / 求最小可行圆环周长

Use `optimize` when you want the exact circular edge coloring number of a concrete signed graph instance.

当你希望直接求出具体符号图实例的最小圆环边色数时，使用 `optimize`。

```powershell
python -m signedcoloring optimize --instance data/instances/star_k1_3_positive.json
```

### 4. Verify a saved witness / 校验已保存的颜色证据

Use `verify` to independently check whether a saved witness really satisfies the incidence-color constraints.

当你需要独立验证某次求解得到的颜色证据是否满足约束时，使用 `verify`。

```powershell
python -m signedcoloring verify --run-dir artifacts/runs/<timestamp>_star_k1_3_positive_optimize
```

## Example Workflow / 示例工作流

The repository already contains several small instances under `data/instances/`. A typical workflow is:

仓库已经在 `data/instances/` 中提供了若干小规模实例。一个典型流程如下：

1. Run a fixed-`r` feasibility check:

```powershell
python -m signedcoloring decide --instance data/instances/cycle_c4_one_negative.json --r 8/3
```

2. Run exact optimization:

```powershell
python -m signedcoloring optimize --instance data/instances/cycle_c4_one_negative.json
```

3. Inspect the generated output directory under `artifacts/runs/`, especially:

   - `summary.json`: the main result summary
   - `witness.json`: the returned base colors and incidence colors
   - `solver_stats.json`: solver statistics such as status, bounds, and elapsed time

运行完成后，到 `artifacts/runs/` 下查看新生成的时间戳目录，其中 `summary.json` 给出主结果，`witness.json` 保存具体颜色证据，`solver_stats.json` 保存求解器状态、上下界和耗时等信息。

## Input Format / 输入格式

Current versions of the solver take a concrete signed-graph instance `(G, σ)` as JSON input.

当前版本的程序输入是一个具体的 `(G, σ)` 实例 JSON，而不是仅输入图类名称。

```json
{
  "name": "single_positive_edge",
  "vertices": ["u", "v"],
  "edges": [
    {"id": "e1", "u": "u", "v": "v", "sign": "+"}
  ]
}
```

- `sign` accepts `"+"`, `"-"`, `"positive"`, `"negative"`, `"plus"`, `"minus"`.
- 为了保持精确性，`r` 这类有理数参数建议以字符串形式提供，例如 `"7/2"` 或 `"3.5"`。

## Project Structure / 项目结构

```text
docs/               Mathematical model and workflow notes
data/instances/     Versioned signed-graph instances
configs/            Parameter-driven sample requests
src/signedcoloring/ Core package: models, IO, solver, verification, CLI
tests/              Unit and integration tests
artifacts/runs/     Raw per-run outputs (ignored by Git)
results/            Curated tables, figures, and notes
scripts/            Thin wrappers only
```

### Source and logic / 源码与求解逻辑

- `src/signedcoloring/`: 核心源码包，包含实例模型、输入输出、Z3 求解器、结果验证和命令行入口。
- `tests/`: 单元测试和集成测试，确保解析、求解和 CLI 行为稳定。

### Inputs and experiment requests / 输入与实验请求

- `data/instances/`: 版本化的符号图实例库，保存具体 `(G, σ)` 输入。
- `configs/`: 参数驱动的样例请求，可用于保存常用运行配置。

### Raw artifacts / 原始运行产物

- `artifacts/runs/`: 每次 `decide` 或 `optimize` 运行产生一个时间戳目录，保存原始结果文件，不纳入 Git 版本控制。

### Curated outputs / 整理后的结果

- `results/`: 存放整理后的表格、图和研究笔记，适合后续汇总与共享。
- `scripts/`: 仅放很薄的辅助启动脚本，不存放核心求解逻辑。

## Documentation / 相关文档

- [docs/model.md](docs/model.md): Mathematical formulation of the incidence-color model.
- [docs/workflow.md](docs/workflow.md): Recommended workflow for running experiments and organizing outputs.

## Artifact Layout / 结果目录说明

Each `decide` or `optimize` run writes a timestamped directory under `artifacts/runs/` containing:

- `request.json`
- `instance.snapshot.json`
- `summary.json`
- `witness.json` when feasible
- `solver_stats.json`

Curated outputs should be copied or summarized into `results/`.
