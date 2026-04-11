# Signed Circular Edge Coloring

**符号图圆环边染色计算 / Exact computation for signed-graph circular edge coloring**

本仓库面向符号图的圆环边染色精确计算，研究在给定具体实例 `(G, σ)` 时，如何判定固定圆环周长 `r` 是否可行，并进一步求出最小可行圆环参数。当前仓库同时支持两条工作流：一条是对具体 signed graph 做 `decide / optimize / verify`，另一条是对固定底图做 `classify-signatures`，先按 switching 或 switching 加图自同构做代表元分类，再把代表元送入现有精确求解流程。

This repository studies exact circular edge coloring on signed graphs. It supports exact feasibility checking and optimization for concrete signed instances `(G, σ)`, and it also supports exact signature classification on a fixed base graph up to switching, or up to switching plus graph automorphism.

This branch now supports both the generic exact classifier and the `native-orbit-search` backend for `switching+automorphism`. That native backend makes large dense classification tasks such as `K_{6,6}` practical at the classification stage; the longer pole then shifts to exact per-class solving.

## Quick Start / 快速开始

Recommended order: install dependencies -> run one solver example -> run one classification example -> inspect files under `artifacts/runs/`.

推荐顺序：安装依赖 -> 跑一个求解示例 -> 跑一个分类示例 -> 查看 `artifacts/runs/` 下的结果文件。

### 1. Install dependencies / 安装依赖

```powershell
python -m pip install -e .[dev]
```

### 2. Check a fixed `r` with `decide` / 用 `decide` 判定固定 `r`

Use `decide` when you already have a candidate circumference and want an exact yes/no answer, together with a witness when feasible.

当你已经有候选圆环周长 `r`，只需要精确判断它是否可行时，使用 `decide`。

```powershell
python -m signedcoloring decide --instance data/instances/star_k1_3_positive.json --r 3
```

### 3. Compute the minimum feasible `r` with `optimize` / 用 `optimize` 求最小可行 `r`

Use `optimize` when you want the exact circular parameter of one concrete signed graph instance.

当你希望直接求出某个具体符号图实例的最小圆环参数时，使用 `optimize`。

```powershell
python -m signedcoloring optimize --instance data/instances/star_k1_3_positive.json
```

### 4. Independently validate a saved witness with `verify` / 用 `verify` 独立校验证据

Use `verify` to independently check whether a saved witness really satisfies the incidence-color constraints.

当你希望独立校验某次求解输出的颜色证据是否满足定义中的约束时，使用 `verify`。

```powershell
python -m signedcoloring verify --run-dir artifacts/runs/<timestamp>_star_k1_3_positive_optimize
```

### 5. Classify signatures on a fixed base graph with `classify-signatures` / 用 `classify-signatures` 对固定底图分类

Use `classify-signatures` when your input is a base graph carrier and you want stable signature representatives for later experiments.

当你想先固定一个底图，再对其所有符号映射类型做稳定分类、选取代表元用于后续实验时，使用 `classify-signatures`。

Classify up to switching only:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json
```

Classify up to switching plus graph automorphism:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json --mode switching+automorphism
```

Keep only classes that contain a representative with exactly `k` negative edges:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json --k 1
```

Classify and immediately optimize every emitted representative:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json --mode switching+automorphism --optimize-representatives
```

Render SVG figures for all optimized classes in an existing classification run:

```powershell
python -m signedcoloring render-classification-figures --run-dir artifacts/runs/<timestamp>_cycle_c4_one_negative_classify-signatures
```

Use the native backend on larger `switching+automorphism` runs:

```powershell
python -m signedcoloring classify-signatures --instance artifacts/runs/k66_base_temp.json --mode switching+automorphism --classification-backend native-orbit-search --jobs 32
```

`--mode switching-only` keeps only switching equivalence. `--mode switching+automorphism` takes a further quotient by automorphisms of the base graph. `--k` keeps only those classes whose switching orbit contains at least one representative with exactly `k` negative edges.

`--mode switching-only` 只按 switching 等价分类；`--mode switching+automorphism` 会进一步按底图自同构取商；`--k` 表示只保留那些 switching 轨道中至少存在一个恰有 `k` 条负边代表的类。

When `--optimize-representatives` is enabled, the command classifies the base graph, runs exact `optimize` on every emitted class representative, and aggregates the class-wise minimum `r` values. The aggregated output records both the smallest and the largest values among those class-wise minima. The current `optimize` path first checks feasibility at the lower bound and only falls back to full optimization when that screening is inconclusive or infeasible.

Classification output now distinguishes two representative notions. `representative_*` remains the canonical representative used for stable class identity. `preferred_*` is a display-oriented representative chosen to minimize the number of negative edges inside the same equivalence class, with lexicographic tie-breaking under the current `edge_order`.

This branch deliberately keeps `classify-signatures` as a single generic entrypoint. It does not add graph-family-specific modes or a complete-bipartite specialized backend.

## Practical Scale Notes / 实际规模说明

The generic classifier remains exact but expensive. On a larger server, single runs may become faster, but the generic `switching+automorphism` path still scales poorly as `beta` grows. The `native-orbit-search` backend changes the classification picture for larger dense base graphs, but representative-level exact solving can still dominate the runtime.

当前的 generic 分类后端仍然是精确的，但代价较高。更强的服务器通常会让单次运行更快一些，不过 generic 的 `switching+automorphism` 路径在 `beta` 增大时仍会很快变重。`native-orbit-search` 已经改变了大规模稠密底图在“分类阶段”的可行性，但代表元层面的精确求解仍然可能成为主要耗时。

- As a practical rule of thumb, `beta <= 9` is usually comfortable under the generic backend.
- `beta ≈ 10-14` is a boundary zone for `generic` and depends heavily on automorphism size, `--k`, and whether `--optimize-representatives` is enabled.
- `beta >= 20` is usually unrealistic for the generic `switching+automorphism` workflow, even on a stronger server.
- Existing anchors match this rule for `generic`: Petersen (`beta = 6`) and `K_{4,4}` (`beta = 9`) are practical; `K_{6,6}` (`beta = 25`) is not.
- Under `native-orbit-search`, `K_{6,6}` classification becomes practical; the main bottleneck then shifts from classification to exact per-class `r` solving.

## Example Workflow / 示例工作流

### Solver-first workflow / 直接求解工作流

For a concrete signed graph instance, a typical workflow is:

对一个具体的符号图实例，一个典型流程是：

1. Run a fixed-`r` feasibility check:

```powershell
python -m signedcoloring decide --instance data/instances/cycle_c4_one_negative.json --r 8/3
```

2. Run exact optimization:

```powershell
python -m signedcoloring optimize --instance data/instances/cycle_c4_one_negative.json
```

3. Inspect the new timestamped directory under `artifacts/runs/`, especially `summary.json`, `witness.json`, and `solver_stats.json`.

### Classification-first workflow / 先分类后求解工作流

When the real object of study is a fixed base graph, the intended workflow is:

当真正的研究对象是一个固定底图时，推荐工作流是：

1. Prepare one carrier instance JSON for the base graph.
2. Run `classify-signatures` to enumerate stable representatives.
3. Inspect `summary.json` and `classes.json`.
4. Choose one or more representatives.
5. Convert those representatives back into concrete signed instances.
6. Run `decide` or `optimize` on those representatives.

The classification command uses the same JSON schema as the solver, but it treats the file as a carrier of the underlying base graph and ignores the stored edge signs.

`classify-signatures` 与求解命令共用同一个 JSON schema，但它把输入文件视为底图载体，只使用图结构，忽略文件中当前写入的边符号。

## Input Format / 输入格式

Current versions of the repository use one JSON schema for both solving and classification:

当前版本对求解和分类共用同一个 JSON 输入格式：

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
- Solver commands read a concrete signed instance `(G, σ)`.
- Classification commands use the same file as a base-graph carrier and ignore the stored signs.
- To preserve exactness, rational parameters such as `r` are best supplied as strings such as `"7/2"` or `"3.5"`.

## Output Files / 输出文件

### Solver runs / 求解运行产物

Each `decide` or `optimize` run writes a timestamped directory under `artifacts/runs/` containing:

- `request.json`
- `instance.snapshot.json`
- `summary.json`
- `witness.json` when feasible
- `solver_stats.json`

`summary.json` records the main result. `witness.json` stores the returned base colors and incidence colors. `solver_stats.json` stores status, bounds, and elapsed time.

### Classification runs / 分类运行产物

Each `classify-signatures` run writes:

- `request.json`
- `instance.snapshot.json`
- `summary.json`
- `classes.json`

`summary.json` records graph size, component count, cycle rank, class counts, bit convention, and the deterministic edge order. `classes.json` stores stable class representatives and machine-readable metadata that can later be converted back into concrete signed instances.

If `--optimize-representatives` is enabled, the same run directory also contains `optimize_runs/`, where each emitted class gets its own nested optimize artifact directory. In that mode, `summary.json` records the global minimum and global maximum among the class-wise `best_r` values, and `classes.json` includes each class representative's `best_r` and witness.

`classes.json` now keeps both the canonical class identity and the display-oriented representative. The canonical fields stay under `representative_*`; the display-oriented, minimum-negative representative stays under `preferred_*`.

When `render-classification-figures` is run on such a classification directory, SVG files are written to `<run-dir>/figures` by default. Each SVG uses the preferred display representative, keeps Cartesian-product vertex grids when labels carry 2D coordinates such as `v00`, `v12`, and shows half-edge colors, edge signs, and edge ids directly on the picture.

## Repository Layout / 项目结构

```text
docs/               Mathematical model and workflow notes
data/instances/     Versioned signed-graph instances
configs/            Parameter-driven sample requests
src/signedcoloring/ Core package: models, IO, solver, verification, classification, CLI
tests/              Unit and integration tests
artifacts/runs/     Raw per-run outputs (ignored by Git)
results/            Curated tables, figures, and notes
scripts/            Thin wrappers only
```

### Source and core logic / 源码与核心逻辑

- `src/signedcoloring/` contains the instance model, JSON IO, exact solver, witness verification, signature classification, and CLI entrypoints.
- `tests/` contains unit and integration tests for parsing, solving, classification, and command-line behavior.

### Inputs and experiment requests / 输入与实验请求

- `data/instances/` stores concrete signed-graph instances and base-graph carriers.
- `configs/` stores parameter-driven request examples.

### Raw artifacts / 原始运行产物

- `artifacts/runs/` stores timestamped raw outputs from parameter-driven runs and is ignored by Git.

### Curated outputs / 整理后的结果

- `results/` stores curated tables, figures, and notes that are meant to be kept and shared.
- `scripts/` contains thin wrappers only and should not hold core mathematical logic.

## Documentation / 相关文档

- [docs/model.md](docs/model.md): solver model and signature-classification model
- [docs/workflow.md](docs/workflow.md): recommended experiment workflow, output organization, and practical scale notes for the current generic backend

## README Maintenance / README 维护原则

Future updates on this branch should keep the README focused on the same core questions: what the project does, how to install it, how to run it, where to find outputs, and how the repository is organized. Sections for files or policies that do not exist in the repository yet should stay out of scope until those materials are actually added.

后续本分支若继续增加功能，README 仍应优先补充这几类信息：项目做什么、如何安装、如何运行、结果看哪里、仓库如何组织。仓库中尚不存在的文件或制度性内容，不应提前扩写成独立章节。
