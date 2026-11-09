---
pretty_name: miniF2F (Lean 4) test subset v1 + PutnamBench (Lean 4.15 snapshot)
language:
  - en
license:
  - apache-2.0
  - mit
task_categories:
  - text-generation
tags:
  - theorem-proving
  - lean4
  - mathlib
  - formal-mathematics
size_categories:
  - n<1K
source_datasets:
  - openai/miniF2F
  - deepseek-ai/DeepSeek-Prover-V1.5 (Lean 4 port of miniF2F)
  - trishullab/PutnamBench
configs:
  - config_name: minif2f
    data_files:
      - split: validation
        path: data/minif2f_valid.jsonl
      - split: test
        path: data/minif2f_test.jsonl
  - config_name: putnambench
    data_files:
      - split: test
        path: data/putnambench.jsonl
---

# Dataset card

<!-- Escrita en ingles porque sigue el formato de Hugging Face; el resto de docs/ va en espanol (D1.8). -->

Problems used to evaluate the multi-agent prover of this project. Every statement is already
formalized in Lean 4 + Mathlib; a proof counts as correct only if the Lean kernel accepts it.

## Lean / Mathlib version

All data is meant to be checked with **Lean v4.15.0** and **Mathlib commit
`9837ca9d65d9de6fad1ef4381750ca688774e608`** (tag v4.15.0), the version pinned in the project
Docker image (decision D1.3).

## Sources and provenance

| Config | Source | Pinned by | Size |
|---|---|---|---|
| `minif2f` | `datasets/minif2f.jsonl` from `deepseek-ai/DeepSeek-Prover-V1.5` (branch `main`), the Lean 4 + Mathlib port of miniF2F (Zheng et al., 2021) | sha256 of the downloaded file: `d6654c88476ff14db19d57dea25bd955a240525fb52171e460f89d98f83d7dd5` | 244 valid + 244 test |
| `minif2f` test subset v1 | `data/test_set.v1.txt`, a stratified sample of the miniF2F test split (see below) | sha256 of the id list: `43e9793670407e09612902fda36731583c65ae72a562033958730543e7bbef7f` | 50 |
| `putnambench` | `lean4/src/*.lean` from `trishullab/PutnamBench` at commit `29a9eae7375f9cefcb13f55b62c385022df5e824` (2025-02-25) | commit + sha256 over the sorted `.lean` files (name and content): `c47997949b1f1eb410845596a71f570b6ef6d9c527d76437a15321e5407e7a98` | 644 (Putnam 1962-2023) |

Reproduce (Python stdlib only, no `datasets`):

```
python -m src.data                 # miniF2F -> data/minif2f_{valid,test}.jsonl
python -m src.data --test-set      # rebuilds data/test_set.v1.txt and checks its sha256
python -m src.data --putnam        # PutnamBench -> data/putnambench.jsonl
python tests/test_data.py          # selection is deterministic and matches the pinned hash
```

Each script aborts if the downloaded content does not match the pinned hash.

## Licenses

- **miniF2F**: the Lean folder of the original `openai/miniF2F` is Apache-2.0 (Metamath part MIT).
  The Lean 4 port is distributed in the DeepSeek-Prover-V1.5 repository, whose code license is MIT
  (`LICENSE-CODE`); the dataset file carries no separate license, so we treat it as MIT on top of
  the Apache-2.0 original and keep the attribution to both.
- **PutnamBench**: Apache-2.0 for the Lean 4 statements (`lean4/LICENSE`). The informal statements
  come from Putnam problems published by the MAA and are redistributed by PutnamBench with the MAA's
  permission; we only keep the docstring already present in each Lean file.

## Data fields

`minif2f` rows: `problem_id`, `split` (`valid`/`test`), `nl_statement` (informal statement),
`formal_statement` (Lean theorem **without** the trailing `:= by sorry`), `theorem_name`. They are
checked against the fixed header `src/data.py:HEADER` (`import Mathlib`, `import Aesop`,
`maxHeartbeats 400000`, `open BigOperators Real Nat Topology Rat`). The source used
`maxHeartbeats 0`; we lowered it so a non-terminating `simp` becomes a `TIMEOUT` instead of a hang.

`putnambench` rows: the same five fields (`split` = `putnam`) plus

- `preamble`: everything between `import Mathlib` and the docstring: the problem's own `open`
  lines, auxiliary `def`s (6 problems) and the solution definition `abbrev putnam_..._solution : T := sorry`.
- `solution_answer`: the reference answer, taken from the `-- ...` comment that follows the
  `_solution` abbrev, or `null` for pure "show that" problems.

### Solution definitions (`abbrev ..._solution`)

328 of the 644 PutnamBench problems ask to *find* a value. The theorem refers to an
`abbrev putnam_XXXX_solution : T := sorry`, and the intended answer is only written in a comment
right below it. In the official PutnamBench setting the prover must produce both the abbrev body and
the proof. Our pipeline only produces proofs, so the answer-bearing problems can be evaluated in two
modes, which must be reported separately and never mixed:

1. **Official**: `import Mathlib` + `preamble` as is (the abbrev stays `sorry`, which the kernel
   rejects as an incomplete answer). Not supported by the current pipeline.
2. **Answer given**: replace `:= sorry` in the abbrev line of `preamble` by `:= <solution_answer>`
   and prove the theorem. This is strictly easier than the official setting and is **not comparable**
   with the PutnamBench leaderboard.

PutnamBench problems must be compiled with `import Mathlib` + their own `preamble`, **not** with the
miniF2F `HEADER`: the extra `open Real Nat ...` there can make names ambiguous.

## Test subset v1 (week 10)

- **Population**: the 244 problems of the miniF2F test split.
- **Size**: 50 (within the planned 40-60).
- **Method**: stratified random sample by source. The stratum comes from the problem id only
  (`mathd_algebra`, `mathd_numbertheory`; `amc12`/`amc12a`/`amc12b` -> `amc12`; `imo`/`imosl` -> `imo`;
  `aime`, `algebra`, `numbertheory`, `induction`). Allocation is proportional to the stratum size,
  rounded, with a minimum of 2 per stratum; inside each stratum the ids are sorted and drawn with
  `random.Random(10).sample` (seed 10 = week 10). Code: `src/data.py:select_test_set`.
- **Sealing (D5.1)**: the selection reads only `problem_id`; statements and proofs are never
  inspected. The runner still refuses `--split test` without `--abrir-test`, and the test split is
  opened once, in week 11:

  ```
  python run.py --config full --split test --abrir-test --problems "$(python -m src.data --test-set-ids)"
  ```

| Stratum | In test split | Selected |
|---|---:|---:|
| mathd_algebra | 70 | 14 |
| mathd_numbertheory | 60 | 12 |
| amc12 | 45 | 9 |
| imo | 20 | 4 |
| algebra | 18 | 4 |
| aime | 15 | 3 |
| induction | 8 | 2 |
| numbertheory | 8 | 2 |
| **Total** | **244** | **50** |

## Bias, limitations and known issues

- **Small n**: 50 problems give wide confidence intervals (about +-14 points at 50% with Wilson);
  the comparison between configurations is exploratory (see design document, risk 2).
- **Stratum floor**: the minimum of 2 slightly over-represents `induction` and `numbertheory`
  (8 problems each). Rates should be reported per stratum as well as overall.
- **Difficulty skew**: miniF2F is dominated by MATH-style (`mathd_*`) high-school problems; the
  olympiad strata (`imo`, `aime`) have only 3-4 problems, too few to say anything per stratum.
- **Contamination**: miniF2F (2021) and Putnam problems are public and appear in many training
  corpora, including those of open provers such as Goedel-Prover-V2 and of the local LLM. Results
  measure the system with these models, not generalization to unseen problems.
- **Formalization errors**: some miniF2F statements are known to be mis-formalized (false, or
  trivially true from contradictory hypotheses). `python -m src.data --check test` only checks that
  each statement compiles with our Mathlib, not that it is faithful.
- **PutnamBench snapshot is not the latest**: PutnamBench `main` (commit `a635813f`, 2026-10) uses
  Lean v4.33.1 and Mathlib `0df444a3`, incompatible with our v4.15.0 image (Mathlib renames and
  parser changes). We pin the last commit on Lean v4.15.0 with exactly our Mathlib commit, which has
  644 problems instead of the current 672 and misses later fixes to statements.
- **Natural-language statements**: miniF2F `nl_statement` comes from the DeepSeek port; PutnamBench
  `nl_statement` is the docstring of the Lean file. Neither is checked against the original
  competition text.
- **PutnamBench is secondary** (D1.7): it is ingested and pinned, but the runner does not load it
  yet and its statements have not been compiled against our image.

## Citation

```
@inproceedings{zheng2022minif2f,
  title={miniF2F: a cross-system benchmark for formal Olympiad-level mathematics},
  author={Zheng, Kunhao and Han, Jesse Michael and Polu, Stanislas},
  booktitle={ICLR}, year={2022}}

@inproceedings{tsoukalas2024putnambench,
  title={PutnamBench: Evaluating Neural Theorem-Provers on the Putnam Mathematical Competition},
  author={Tsoukalas, George and Lee, Jasper and Jennings, John and Xin, Jimmy and Ding, Michelle
          and Jennings, Michael and Thakur, Amitayush and Chaudhuri, Swarat},
  booktitle={NeurIPS Datasets and Benchmarks}, year={2024}}
```
