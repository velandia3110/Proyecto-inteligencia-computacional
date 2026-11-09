---
license: apache-2.0
language:
- en
tags:
- lean4
- theorem-proving
- minif2f
- multi-agent
pretty_name: mathagents traces (miniF2F, Lean 4 verified)
configs:
- config_name: test_set
  data_files: test_set.jsonl
---

# mathagents: execution traces on miniF2F

Raw traces of a multi-agent system (planner, retriever, generator, autoformalizer,
verifier, critic) that proves miniF2F problems, where a problem counts as solved **only if
the Lean 4 kernel accepts the assembled proof** with no `sorry` and no axioms outside
`{propext, Classical.choice, Quot.sound}`.

## Contents

| Path | What it is |
|---|---|
| `traces/*.jsonl` | One file per configuration run. One `header` line (seed, models, Mathlib commit, repo commit), one `call` line per LLM call, `event` lines, and one `result` line per problem. |
| `test_set.jsonl` | The miniF2F problems evaluated in the traces (`problem_id`, `nl_statement`, `formal_statement`). The test split was opened once. |
| `prompts/*.md` | Versioned prompts, frozen before the test set was opened. |
| `results/` | `analysis.md` and `analysis.json` produced by `python -m src.analysis traces/*.jsonl`. |
| `MANIFEST.sha256` | Checksums of every file above. |

## Configurations (ablation)

| Config | Description |
|---|---|
| `baseline_a` | One prompt to the prover, whole proof, one call |
| `baseline_b` | Natural-language chain of thought with self-assessment, then formalized |
| `agents_only` | Multi-agent, no retrieval, no critic |
| `no_critic` | Multi-agent with retrieval, no critic |
| `full` | Full system |

## Results

See `results/analysis.md`. Solve rates are reported with 95% Wilson intervals; pairwise
comparisons use exact McNemar with Bonferroni correction plus paired-bootstrap confidence
intervals for the rate difference. With a test set of roughly 50 problems the study is
**exploratory**: read effect sizes and intervals, not only p-values.

## Known limitations

- Planner, generator and critic run on a small local model (`qwen3:4b-instruct` via Ollama),
  so absolute solve rates are not comparable with systems that use frontier API models.
- The prover runs without its built-in self-correction loop, so baselines are weaker than the
  off-the-shelf prover.

## Reproducing

Every number is aggregated from the traces; nothing is computed by hand. Kernel verification
requires the project's Docker image (Lean 4 + pinned Mathlib commit).
