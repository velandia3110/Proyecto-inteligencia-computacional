---
title: "Plausible Is Not Proved: A Budgeted Multi-Agent System for Olympiad Mathematics Verified by the Lean 4 Kernel"
author: "[[AUTHORS: team names, Universidad Pedagógica y Tecnológica de Colombia (UPTC), Artificial Intelligence course]]"
date: "[[DATE: submission date]]"
bibliography: ../references.bib
suppress-bibliography: true
---

<!--
Status of this draft (2026-11-09). The experiments of week 11 have NOT been run: the prover
(Goedel-Prover-V2-8B) is not yet served. Every result that does not already exist in
docs/status.md is an explicit marker of the form [[RESULT: ...]]. Do not replace a marker with
anything that does not come from aggregating runs/*.jsonl with `python -m src.analysis` (D5.3).
Numbers that are already measured (corpus size, recall@k, 244/244, test counts) are used as is.
Citations use pandoc syntax [@key] against docs/references.bib; the reference list at the end is
written by hand so the Markdown reads on its own (hence suppress-bibliography).
-->

## Abstract

Large language models (LLMs) write mathematical derivations that read well and are often wrong,
and the confidence they report about their own output is not a reliable signal of correctness. We
build a system that treats this as a design constraint rather than a nuisance. Six agents
(Planner, Retriever, Generator, Autoformalizer, Verifier and Critic), orchestrated as an explicit
state graph in LangGraph, decompose an olympiad problem into subgoals, retrieve Mathlib premises,
sketch informal proofs, translate them into Lean 4 tactics and repair failures, but only the Lean 4
kernel decides whether a problem is solved: a proof counts if and only if the assembled theorem
compiles with no `sorry` and no axiom outside the core set. Two design choices separate the system
from prior sketch-then-prove pipelines. First, the Planner's decomposition is itself a Lean
skeleton that is compiled before any subgoal is attempted (`VERIFY_SKELETON`), so a bad plan is
rejected mechanically instead of being discovered after the budget is spent. Second, every model
call goes through a hard, auditable budget of 20 calls per problem. The whole stack runs locally at
zero marginal cost per token: a 4B instruction model (Qwen3-4B-Instruct, via Ollama) plans,
sketches and critiques, and Goedel-Prover-V2-8B formalizes. On a sealed, stratified test set of
50 miniF2F problems opened once, the full system solves [[RESULT: full, solved/50 and solve rate,
Wilson 95% CI]], against [[RESULT: baseline_a, solved/50 and solve rate, Wilson 95% CI]] for a
single-call prover baseline. An ablation over five configurations isolates the contribution of
retrieval and of the Critic ([[RESULT: one-sentence summary of the pairwise McNemar/bootstrap
outcome, e.g. which differences have CIs excluding 0]]). When the same 4B model is asked to judge
its own natural-language proofs, the kernel rejects [[RESULT: baseline_b false-positive rate,
x/y self-declared-correct proofs rejected by the kernel]] of the proofs it declared correct; these
are the false positives a verifier-in-the-loop design avoids. The study is exploratory by design
(n = 50, Bonferroni-corrected pairwise tests) and we report effect sizes with intervals rather than
significance claims.

## 1. Introduction

Chain-of-thought prompting made LLMs visibly better at multi-step mathematics
[@wei2022chain; @wang2023selfconsistency], and benchmark scores on informal mathematics such as
MATH [@hendrycks2021math] have risen fast. Those benchmarks score the final answer. A derivation
that reaches the right number through an invalid step counts as correct, and a derivation that
contains a false lemma stated with confidence is indistinguishable, to the metric, from a sound
one. For an assistant that is meant to help a person do mathematics, this is the wrong failure
profile: errors are hidden precisely where the output looks most convincing.

Formal proof assistants invert the situation. The Lean 4 kernel [@demoura2021lean4] accepts or
rejects a proof in bounded time, and its decision does not depend on how persuasive the proof
looks. Generating and verifying are therefore asymmetric regimes: generation is cheap, flexible
and frequently wrong; verification is rigid, slower, and not open to argument. The premise of this
project is to exploit that asymmetry rather than to fight it. We let LLM agents be as creative and
as wrong as they like during generation, and we route every claim of success through the kernel.

The single success criterion follows directly from that premise: *a problem is solved if and only
if the Lean 4 kernel accepts the assembled proof, with no `sorry` and no axiom outside
{`propext`, `Classical.choice`, `Quot.sound`}*. Nothing else in the system, including the agents'
own assessments, can mark a problem as solved.

The system has six agents with typed JSON contracts. A Planner turns the problem into a Lean
skeleton with one `have … := by sorry` per subgoal; a Retriever returns the *k* Mathlib premises
closest to each subgoal under a dense embedding; a Generator writes informal proof sketches; an
Autoformalizer (a dedicated prover model) translates a sketch into Lean tactics; a deterministic
Verifier returns one of seven verdicts; and a Critic classifies failures and routes the retry. The
agents are orchestrated as an explicit state graph, which is itself a deliverable: every edge is a
documented decision, and every model call is logged.

Draft, Sketch, and Prove [@jiang2023dsp] already chains informal draft, formal sketch and gap
filling; LeanDojo [@yang2023leandojo] already retrieves premises; Baldur [@first2023baldur] already
repairs proofs from the compiler's error message. We do not claim to beat the state of the art in
pass@k, and the project is not evaluated on raw throughput. What none of those three systems
combines, and what this work contributes, is:

1. **Verifying the decomposition before proving anything.** Because the plan is Lean code, the
   kernel checks that the subgoals imply the theorem (`VERIFY_SKELETON`). Decomposition becomes
   falsifiable instead of hopeful.
2. **An explicit, auditable call budget as a design constraint.** A hard ceiling of 20 LLM calls
   per problem, enforced by an exception rather than a warning, with every call written to a JSONL
   log from which all metrics are aggregated.
3. **Measuring the false positives that verification avoids.** A baseline asks the model to judge
   its own proof; formalizing the same proofs lets us count how often "I am confident this is
   correct" is rejected by the kernel.

A practical constraint shaped the final system: there was no budget for API calls. The planning,
sketching and critique agents therefore run on a 4B-parameter local model, and the prover runs as a
self-hosted 8B model. This makes absolute solve rates incomparable with systems built on frontier
API models, but it keeps the ablation internally valid, since all five configurations share the
same models, and it makes the system reproducible on modest hardware.

The rest of the report is organized as follows. Section 2 reviews related work by theme and ties
each line of work to a design decision. Section 3 describes the architecture, the state graph, the
retriever and its measured recall, the budget, the models and the experimental protocol. Section 4
reports results; Section 5 discusses them; Section 6 covers ethical considerations; Section 7
lists limitations; Section 8 concludes.

## 2. Related Work

**Language models.** The Transformer [@vaswani2017attention] is the substrate of every model we
use; its attention cost grows with context length, which in our setting bounds how many retrieved
lemmas fit in a prompt. In-context learning [@brown2020language] and instruction tuning
[@ouyang2022training] are the two properties we rely on instead of training: no model in this
project is fine-tuned, and each agent's behavior is specified by a versioned prompt and a JSON
contract that an instruction-tuned model can be asked to respect.

**Reasoning chains.** Chain-of-thought prompting [@wei2022chain] is the mechanism behind our
Generator and behind baseline B. It is also the source of the project's central caution: a chain
of thought improves plausibility and often accuracy, but nothing in it certifies a step.
Self-consistency [@wang2023selfconsistency] samples several chains and takes a majority; our
Generator applies the same idea to proof sketches, sampling two sketches and choosing the one whose
suggested tactics agree most with the other (Jaccard overlap), because sketches with the same
answer can differ in every word. Self-consistency multiplies the number of calls, which is why we
use n = 2 only on a subgoal's first attempt (Section 3.8). Tree of Thoughts [@yao2023tree]
generalizes the chain into a search tree. We left it out of scope: a chain with verified
replanning already covers the reasoning axis of the course, and tree search would multiply calls
beyond the budget. MATH [@hendrycks2021math] is the standard reference for informal mathematical
performance, and it illustrates the measurement problem we start from: final-answer matching cannot
detect a false derivation.

**Agentic and multi-agent systems.** ReAct [@yao2023react] interleaves reasoning with actions
whose observations return to the model. Our FORMALIZE → VERIFY → CRITIQUE loop is a ReAct loop in
which the observation is produced by a proof kernel rather than by a fuzzy tool. Reflexion
[@shinn2023reflexion] feeds verbal feedback about failures back into the next attempt; it is the
direct ancestor of our Critic. The difference is the source of the feedback: in Reflexion the model
criticizes itself, while here the error message comes from the compiler and the Critic only
classifies it and writes a one-sentence diagnosis. AutoGen [@wu2024autogen] organizes agents as a
conversation. We considered it and chose LangGraph [@langgraph] instead, because a typed state and
explicit edges make the control flow inspectable and checkpointable, and because the state graph
is a graded artifact that a conversational framework would hide behind roles. Generative Agents
[@park2023generative] supply the vocabulary of agents with memory and reflection; our per-subgoal
attempt history plays the role of their episodic memory.

**Embeddings and retrieval-augmented generation.** Retrieval-augmented generation
[@lewis2020rag] conditions a generator on documents fetched from an external store, with the
argument that external knowledge reduces hallucination. In theorem proving, the "documents" are
Mathlib lemmas and the hallucination has a precise signature: a lemma name that does not exist,
which Lean reports as `unknown identifier`. Dense passage retrieval [@karpukhin2020dpr] established
inner-product search over learned embeddings as a strong retriever; our Retriever is a dense
retriever in that sense. For the encoder we chose BGE-M3 [@chen2024m3], which is multilingual and
handles long inputs, both relevant because a pretty-printed Lean type is long and is not prose. E5
[@wang2022e5] was the alternative considered. For search we use FAISS [@johnson2021faiss] with an
exact inner-product index rather than an approximate one: with under 2·10^5 premises exact search
is fast enough, and it guarantees that no recall failure can be blamed on the index.

**Formal verification and neural theorem proving.** Lean 4 [@demoura2021lean4] has a small trusted
kernel, which is what makes the word "verified" defensible: we trust the kernel and nothing else.
Mathlib [@mathlib2020] is both our premise corpus and the reason retrieval is necessary: it is
large, its naming conventions are systematic but not guessable, and models confidently invent
names that follow the convention but do not exist. Polu and Sutskever [@polu2020generative] showed
that a generative language model can produce formal proofs and introduced the pass@k evaluation
that the field still uses. Autoformalization [@wu2022autoformalization] defined the task of
translating informal mathematics into formal statements and documented its failure rate; that is
why our verdicts separate a failure to *translate* (`FORMALIZATION_FAILED`) from a failure of the
*mathematics* (a kernel verdict). Draft, Sketch, and Prove [@jiang2023dsp] is the closest work to
our architecture: an informal draft becomes a formal sketch with open gaps, which an automated
prover then closes. Our system differs in three ways: the sketch is compiled before the gaps are
attempted, the stages are explicit agents with contracts and a budget, and failures are routed by
error class. LeanDojo [@yang2023leandojo] provides tooling, a premise corpus and annotations of
which premises each Mathlib proof uses; we planned to use those annotations as retrieval ground
truth, but they are tied to a different Mathlib commit from ours, so we extracted our own corpus and
ground truth from the pinned commit (Section 3.5). Baldur [@first2023baldur] repairs whole proofs
by conditioning on the error message, which is direct evidence for our requirement that the raw
Lean error be injected into the retry prompt. DeepSeek-Prover-V1.5 [@xin2025deepseekprover] uses
proof-assistant feedback for reinforcement learning and tree search, and is also the source of the
Lean 4 port of miniF2F we use. Goedel-Prover-V2 [@lin2026goedel] is the prover we chose for
formalization: its 8B model reports 84.6% pass@32 on miniF2F while being far smaller than the
671B-parameter prover it is compared against, and it can be self-hosted. It also ships a
compiler-guided self-correction mode, which overlaps with our Critic; Section 3.7 explains how we
neutralize that overlap.

**Benchmarks.** miniF2F [@zheng2022minif2f] is our primary benchmark. Its statements are already
formalized and audited, which removes a risk we could not afford to measure: mis-formalizing the
statement itself. PutnamBench [@tsoukalas2024putnambench] is the secondary benchmark at a higher
difficulty band. AlphaGeometry [@trinh2024alphageometry] closes the review: a neuro-symbolic
system in which a language model proposes constructions and a symbolic engine checks them reached
olympiad level in geometry, which is the strongest existing evidence that coupling a generator to a
rigid checker is a productive design, not only a safe one.

**Positioning.** None of the systems above claims, and neither do we, that orchestration beats a
stronger model. Our contribution is methodological: a decomposition that is checked before it is
trusted, a budget that is enforced before it is reported, and a measurement of what
self-assessment misses.

## 3. Methodology

### 3.1 Task and success criterion

The input is a miniF2F problem: a natural-language statement and its Lean 4 formal statement. The
output is either a Lean proof accepted by the kernel or a failure with a recorded cause. Success is
decided only by the Verifier on the assembled theorem, with three conditions: the code compiles,
it contains no `sorry`, and the axioms it depends on are a subset of {`propext`,
`Classical.choice`, `Quot.sound`}. In addition, before any proof reaches the kernel, the system
checks that the theorem statement in the candidate is identical to the original. Without that
check a model can prove an easier theorem that compiles cleanly; such candidates receive the
verdict `STATEMENT_CHANGED` and are never sent to the kernel. This check was not in the original
design; it was added in weeks 3–4 when building the baselines.

### 3.2 Architecture: six agents

| Agent | Input | Output | Mechanism |
|---|---|---|---|
| Planner | NL statement + formal statement | Lean skeleton, one `have … := by sorry` per subgoal | Qwen3-4B-Instruct |
| Retriever | subgoal type | top-*k* Mathlib premises | BGE-M3 + FAISS `IndexFlatIP` |
| Generator | subgoal + hypotheses + premises | *n* informal sketches with tactic hints | Qwen3-4B-Instruct |
| Autoformalizer | sketch + premises + subgoal as a standalone lemma | Lean 4 tactic block | Goedel-Prover-V2-8B |
| Verifier | Lean code | one of seven verdicts + raw kernel output + axioms | deterministic, Lean REPL |
| Critic | verdict + raw error + attempt history | error class + one-sentence diagnosis | Qwen3-4B-Instruct |

Every agent's output crosses a module boundary as JSON validated against a JSON Schema (draft
2020-12) in `docs/contracts/`. The Verifier is not an LLM, but it has a contract like the others,
because the requirement that interfaces be typed applies to the boundary and not to the mechanism
behind it. Every prompt is a versioned file in `prompts/`; there are no prompt strings in the code.
A single function performs every model call: it charges the budget, renders the prompt, calls the
backend and writes one JSONL line with the run, configuration, problem, agent, attempt, model,
seed, token counts, latency, decision and verdict. The log header records the seed, the Mathlib
commit, the embedding model, the LLM versions and the repository commit, read from the
environment rather than written by hand. No metric in this report is computed by hand; all are
aggregated from these logs.

### 3.3 State graph

The graph extends the six states of the original proposal (PLAN, RETRIEVE, GENERATE, FORMALIZE,
VERIFY, CRITIQUE) with two checks the proposal lacked: `VERIFY_SKELETON` after planning, and the
pair `ASSEMBLE`/`VERIFY_FINAL` at the end.

```
PLAN -> VERIFY_SKELETON --(fails, replan once)--> PLAN
VERIFY_SKELETON --(compiles with sorries)--> RETRIEVE -> GENERATE -> FORMALIZE -> VERIFY
VERIFY --OK, subgoals left--> RETRIEVE (next subgoal)
VERIFY --OK, last subgoal--> ASSEMBLE -> VERIFY_FINAL --OK--> SOLVED
VERIFY / FORMALIZE --failure--> CRITIQUE
CRITIQUE --SYNTAX--> FORMALIZE (same sketch, error shown)
CRITIQUE --MISSING_LEMMA--> RETRIEVE (larger k)
CRITIQUE --UNSOLVED_GOALS--> GENERATE (new sketch)
CRITIQUE --PLANNING_ERROR--> PLAN (replan once per problem)
CRITIQUE --budget exhausted or unrecoverable--> FAILED
VERIFY_FINAL --fails--> PLAN (replan once, full system only)
```

**Why `VERIFY_SKELETON`.** The Planner does not emit a list of steps in prose; it emits a Lean
theorem in which each step is a `have` closed by `sorry`, followed by a closing tactic:

```lean
theorem mathd_algebra_478 (b h v : ℝ) (h₀ : 0 < b ∧ 0 < h ∧ 0 < v)
    (h₁ : v = 1/3 * (b*h)) (h₂ : b = 30) (h₃ : h = 13/2) : v = 65 := by
  have step1 : b * h = 195 := by sorry
  have step2 : v = 1/3 * 195 := by sorry
  linarith [step1, step2]
```

If this block compiles (with `sorry` warnings allowed), the subgoals logically imply the theorem:
the decomposition is valid before anything is proved. If it does not compile, the Planner failed
and is asked once more, with the kernel error pasted into the prompt. Before compilation the code
checks three things that the kernel alone would not catch: the theorem statement is unchanged;
each declared subgoal appears in the skeleton as a single-line `have name : … := by sorry`; and the
number of `sorry` occurrences equals the number of subgoals, so that no `sorry` hides in the
closing tactic, which would let a skeleton "prove" the theorem by cheating. Each subgoal's statement
is then taken from the skeleton text, not from the JSON the Planner returned, because the skeleton
is what the kernel checked and the two can disagree.

**Why `ASSEMBLE`/`VERIFY_FINAL`.** A subgoal verified in isolation does not guarantee that the
assembled theorem compiles: the local context, hypothesis names and elaboration can change. Each
subgoal is proved as a standalone lemma whose hypotheses are the theorem's binders plus the
statements of the earlier subgoals. `ASSEMBLE` substitutes every `sorry` with its proof and the
whole theorem is compiled again. Only `VERIFY_FINAL` can produce `SOLVED`.

**Retries without and with the Critic.** In the configurations without a Critic, a failed subgoal
is retried *blindly*: new sketches, without showing the model the Lean error, up to two attempts
per subgoal. This was a deliberate decision. If the configuration without a Critic did not retry at
all, the ablation would measure "retrying versus not retrying" and not what reading the error
contributes. With the Critic, the same cap of two attempts per subgoal applies, and the retry
carries the failed proof, the raw error and the Critic's diagnosis. With the Critic the system may
also replan at most once per problem, either because the Critic classifies the failure as a
planning error or because `VERIFY_FINAL` fails after every subgoal was closed in isolation (in
which case there is no single subgoal to blame and the Critic is not called).

The graph is implemented with LangGraph's `StateGraph`, a typed state, and an in-memory
checkpointer after every node. Resources that are not serializable (REPL process, model backends,
log, budget) are closed over by the graph rather than stored in the state.

### 3.4 Verdicts

The Verifier answers with one of seven verdicts, not with "compiles / does not compile":

| Verdict | Condition | Why it exists |
|---|---|---|
| `OK` | compiles, no `sorry`, axioms ⊆ allowed set | the only path to `SOLVED` |
| `SORRY` | compiles but contains `sorry` | otherwise a `sorry` counts as a proof and the main metric is falsifiable |
| `AXIOM` | depends on an axiom outside the allowed set | `axiom cheat : False` proves anything and compiles |
| `SYNTAX_ERROR` | parse or elaboration error | cheap retry with the same sketch |
| `MISSING_LEMMA` | `unknown identifier` / `unknown constant` | a hallucinated lemma name; a direct signal to the Retriever |
| `UNSOLVED_GOALS` | open goals at the end of the proof | the sketch is wrong, not the syntax |
| `TIMEOUT` | wall-clock limit exceeded or the process dies | `decide` and `simp` may not terminate |

Outside the kernel, the graph records four further outcomes: `STATEMENT_CHANGED` (Section 3.1),
`FORMALIZATION_FAILED` (the prover returned no tactic block, or used `sorry`/`admit`),
`PLANNING_ERROR` (no valid skeleton after one replan) and `BUDGET_EXHAUSTED`. For the error
taxonomy, failures are grouped in five classes: syntax, missing lemma, unsolved goals, timeout and
planning error.

Testing against the real kernel changed the classifier. Lean 3 syntax (`begin … end`) is reported
by Lean 4 as `unknown identifier 'begin'`, and the first classifier read it as a missing lemma,
which would have sent the system to retrieve more lemmas for what is a syntax problem; it is now
classified as syntax. A stack overflow kills Lean without a response, and was first counted as a
syntax error; it now counts as `TIMEOUT` and the REPL is restarted.

### 3.5 Retriever

Let 𝓜 be the Mathlib premise corpus and *e* the BGE-M3 encoder (d = 1024). For a subgoal *g*, the
Retriever returns the set of size *k* that maximizes the summed cosine similarity:

$$R_k(g) = \arg\max_{S \subset \mathcal{M},\ |S| = k} \sum_{\ell \in S} \frac{\langle e(g), e(\ell)\rangle}{\lVert e(g)\rVert\,\lVert e(\ell)\rVert}.$$

Because the maximum of a sum over fixed-size subsets is reached by the *k* largest terms, R_k(g) is
exactly the top-*k* by cosine. Vectors are L2-normalized at indexing and query time, so inner
product equals cosine, and a FAISS `IndexFlatIP` returns R_k(g) exactly. Each premise is indexed as
`"{name} : {pretty-printed type}\n{docstring}"`; the type is the strong signal, and the docstring is
a bridge from natural language to formal statements.

**Corpus.** We extracted the corpus from the same Mathlib commit the Verifier uses (commit
`9837ca9d`, tag v4.15.0) with a Lean metaprogram: 252,002 theorems, reduced to 179,269 after
removing lemmas Lean generates automatically (`sizeOf_spec`, constructor injectivity, equation
lemmas), which nobody writes by hand and which pollute the top-*k*. Extraction took 23 minutes in
Docker; encoding and indexing the 179,269 × 1024 matrix took about 34 minutes on a 4 GB GPU.

**Ground truth and recall@k.** We evaluated the Retriever in isolation on 1,000 Mathlib theorems
sampled with seed 0. The query is the theorem's type and the relevant set is the set of theorems
that appear in its proof term, extracted from the same commit:

$$\text{recall@}k = \frac{1}{N}\sum_{t=1}^{N}\frac{|\mathrm{Rel}(t)\cap R_k(t)|}{|\mathrm{Rel}(t)|}.$$

The original design used LeanDojo's premise annotations as ground truth; we switched because
LeanDojo's data is tied to a different Mathlib commit and names do not match. The measured curve
is:

| k | 5 | 10 | 20 | 50 |
|---|---|---|---|---|
| recall@k | 0.173 | 0.224 | 0.287 | 0.362 |

These numbers are low and we report them as they are. A manual probe shows where much of the
problem comes from. When the query contains a name (`Nat.Prime p → 2 ≤ p`), the exact lemma is
ranked first with a similarity of 0.85; when the query is purely symbolic (`0 ≤ x ^ 2`,
`a * b = 0 → a = 0 ∨ b = 0`), obvious lemmas such as `sq_nonneg` or `mul_eq_zero` do not even
appear in the top five. Since the indexed text starts with the lemma name, the encoder leans
heavily on names. The ground truth is also noisy, because a proof term contains what tactics insert
internally, which no one would write by hand. On this curve a reasonable *k* lies between 10 and 20;
the cost of a larger *k* is only prompt length. The configurations with retrieval use *k* = 10, and
when the Critic classifies a failure as a missing lemma, *k* is doubled for that subgoal (10 → 20,
capped at 50).

**Hallucinated names.** When the Generator cites a lemma that was not in the list it received, the
name is removed from the sketch and logged as an event. This lets us count name hallucinations
without inflating the call count.

### 3.6 Generator and self-consistency

For each subgoal the Generator produces *n* sketches, each with numbered informal steps, tactic
hints and the lemmas it intends to use. With *n* = 2 the selected sketch is the one whose tactic
hints have the highest Jaccard overlap with the others,
J(T_i, T_j) = |T_i ∩ T_j| / |T_i ∪ T_j|, and the agreement *a* is the fraction of sketches whose
overlap with the winner is at least 0.5. We compare tactics and not words because two sketches can
say the same thing in different words. A malformed sketch does not abort the subgoal if another one
is valid.

### 3.7 Critic and decision D2 (overlap with the prover's self-correction)

Goedel-Prover-V2 has a self-correction mode guided by Lean compiler feedback. That is exactly the
Critic's function. If it were left on, the ablation "without Critic" would compare "external Critic
plus internal self-correction" against "internal self-correction", and the measured effect would
not be the Critic's. We checked the model's official documentation: self-correction is a loop
*outside* the model, in which the compiler error is passed back in a new call; a single call is the
"standard mode". We therefore invoke the prover in one pass per formalization: it receives the
sketch and the lemmas and returns tactics, and never sees the compiler error on its own. Every
retry cycle passes through our Critic, which is our code and is instrumented in the log. The
alternative, treating the prover's self-correction as part of the baseline, was rejected because
it would make the call count unauditable.

The Critic does not choose the recovery action. It classifies the failure (syntax, missing lemma,
unsolved goals, timeout, planning error, budget exhausted) by the first error Lean reports, and
writes a one-sentence diagnosis that is injected into the retry prompt together with the raw error.
The action, whether the failure is recoverable, and the new *k* are set by code from a fixed table:
syntax → reformalize the same sketch; missing lemma → retrieve more; unsolved goals → new sketch;
timeout → reformalize once, then abandon; planning error → replan; budget exhausted → abandon. If
the Critic's output does not validate against its contract, the class implied by the Verifier's
verdict is used instead. Keeping the policy in code means the Critic's contribution is its
classification and its diagnosis, both of which are logged and can be audited.

The honest consequence of D2 is that our prover baseline is weaker than the prover "out of the
box". We state it in Section 7 and report the published self-correction number as an external
reference only.

### 3.8 Call budget (decision D3)

The non-functional requirement is at most 20 LLM calls per **solved** problem. The cost of a
problem in the full system is

```
plan(1) + VERIFY_SKELETON(0) + Σ_subgoals [ generate(n) + formalize(1) + critique(≤1) ] × attempts
```

A naive worst case with five subgoals, *n* = 2 and three attempts is about 60 calls. Three rules
bring it under the ceiling: *n* = 2 only on a subgoal's first attempt and *n* = 1 on retries
(self-consistency where it pays); early cut-off when the failure is unrecoverable (a planning error
after one replan, or a repeated timeout), and no retry is started if the remaining budget cannot
afford it; and, since the requirement is stated over solved problems, abandoned problems are
reported separately. The attempt cap was set to two per subgoal in all three multi-agent
configurations, not three, so that the only differences between them are retrieval and the
Critic. The ceiling is implemented as a `Budget` object with `max_llm_calls = 20` whose `spend`
method raises an exception when exceeded; the run records `BUDGET_EXHAUSTED`. Without the
exception the requirement would be an aspiration.

### 3.9 Local models

The original design used a frontier model through an API for planning, sketching and critique.
Because the API charges per token and the project had no budget for it, those three agents and
baseline B were moved to Qwen3-4B [@yang2025qwen3] served locally by Ollama [@ollama]; only the
backend module changed. We use the *instruct* variant with thinking disabled, an 8K context
window, and output constrained to JSON. Both settings were forced by a smoke test: the reasoning
variant spent its full 8,192-token allowance (about 29 minutes on the 4 GB GPU) thinking without
producing an answer, and without forced JSON the model reasoned in the text until it ran out of
tokens. The instruct variant returned valid JSON with every contract field, but its first skeleton
lacked the closing tactic, which `VERIFY_SKELETON` would reject; the kernel catching this is the
system working as intended, but it signals that the skeleton rate may be the bottleneck.

The Autoformalizer is Goedel-Prover-V2-8B (Apache-2.0), prompted in the format it was trained on:
the subgoal is presented as a standalone lemma and the code, not the model, assembles the contract
JSON. It is sampled at temperature 0.6. It does not fit in the 4 GB GPU, so it is served through an
OpenAI-compatible endpoint, either with vLLM [@kwon2023vllm] on a borrowed GPU or quantized in
Ollama split between GPU and CPU ([[RESULT: serving setup actually used in week 11 — hardware,
precision/quantization, endpoint]]).

### 3.10 Lean environment and decision D4

The official schedule placed the Lean environment in week 3. We moved it to week 1 without moving
any deliverable, because it was the highest technical risk of the project (toolchain, Mathlib,
REPL and Python bridge) and the only one that could invalidate the whole scope. The gate was
`theorem test : 2 + 2 = 4 := by norm_num` verified from Python; if it did not pass, the scope would
be renegotiated. The gate closed late, in week 3, and printed `veredicto=OK axiomas=['propext']`.

The environment is a Docker image with Lean 4.15, Mathlib pinned at commit
`9837ca9d65d9de6fad1ef4381750ca688774e608` (tag v4.15.0, prebuilt cache) and the community REPL
[@leanrepl] at the matching tag. We talk to the REPL directly from a small Python client using only
the standard library, because the JSON protocol is stable and because we needed control over
process life cycle for a pool of reusable REPLs. Every problem shares a header (`import Mathlib`,
`import Aesop`, `set_option maxHeartbeats 400000`) that each REPL loads once. The heartbeat limit
is 400,000 rather than 0 because with 0 a non-terminating `simp` hangs the process instead of
returning `TIMEOUT`; in practice the 120-second wall-clock limit is always the one that fires,
since on our machine Lean spends about 20,000 heartbeats every 7 to 12 seconds.

Connecting the real kernel exposed six bugs that fabricated REPL responses had hidden. The REPL
launched without `lake env` loaded an empty environment silently: `import Mathlib` did not fail,
it simply loaded nothing. Unicode characters escaped as surrogate pairs in JSON (for example `𝓝`)
caused syntax errors. Lean 3 syntax was classified as a missing lemma. A stack overflow was
classified as a syntax error. After a timeout, killing `lake` left the REPL child alive with up to
3 GB of memory; the whole process group is now killed. And the Planner's JSON statement of a
subgoal could differ from the skeleton text. Each REPL shares the roughly 3.9 GB of memory-mapped
Mathlib with the others and needs 0.3–0.4 GB of its own, so 2 or 3 workers fit in the 8 GB given
to Docker. The tests that do not need Lean or models run in continuous integration on every push;
the tests against the real kernel are run by hand, because building the image takes about 20
minutes and several gigabytes.

### 3.11 Data

We use the Lean 4 port of miniF2F published with DeepSeek-Prover-V1.5 [@xin2025deepseekprover],
pinned by SHA-256: 244 development (validation) problems and 244 test problems. All 244
development statements compile with our Mathlib commit. The test set for the experiment is a
stratified sample of 50 problems from the miniF2F test split, allocated proportionally to the
size of each source (e.g. `mathd_algebra`, `amc12`, `imo`) with at least two per source, drawn
with a fixed seed using *only the problem identifiers*: statements and proofs did not enter the
selection. The list of identifiers is versioned and checked against a hash. PutnamBench is the
secondary benchmark ([[RESULT: whether PutnamBench problems were run in week 11, and how many]]).

### 3.12 Experimental protocol

**Configurations.** Five configurations isolate the contribution of each component:

| # | Configuration | Flag | Models |
|---|---|---|---|
| 1 | Baseline A: one prompt → full Lean proof, one prover call | `baseline_a` | prover |
| 2 | Baseline B: chain-of-thought in natural language with self-evaluation, then formalized by one prover call | `baseline_b` | Qwen3-4B + prover |
| 3 | Multi-agent, no retrieval, no Critic | `agents_only` | both |
| 4 | Multi-agent with retrieval, no Critic | `no_critic` | both + BGE-M3 |
| 5 | Full system | `full` | both + BGE-M3 |

Baseline A uses the same prover as the system's Autoformalizer, so the comparison measures the
architecture and not a change of model. Baseline B records the model's own verdict on its proof
(`self_verdict`) before formalization; this is the data for the false-positive metric. A sixth
flag, `plan_only`, runs only PLAN and `VERIFY_SKELETON` and measures the skeleton validity rate.

**Development and test.** All tuning (prompt revisions, the choice of *k*, the Planner prompt if
the skeleton rate is too low) happens on the development split. Prompts were frozen in week 10.
The runner refuses to open the test split without an explicit flag, and the test set is opened
exactly once, in week 11, with every configuration run on the same 50 problems and the same seed.
Touching a prompt after the test set is opened would invalidate the experiment. The target band
for the full system on development is a 30–60% solve rate: below it all configurations score near
zero and the ablation measures nothing; above it they all saturate. The week 5–6 gate required
skeletons to compile on more than 70% of development problems. That threshold is our own, not a
literature value: since a problem without a valid skeleton is lost, the skeleton rate is a ceiling
on the solve rate, and the Planner must sit well above the target band not to be the bottleneck.

**Metrics.** (i) *Solve rate*, the fraction of problems for which `VERIFY_FINAL` returns `OK`;
(ii) *LLM calls per solved problem* and the count of abandoned problems; (iii) *false positives
avoided*: among baseline B proofs that the model declared correct, the fraction the kernel
rejects; (iv) *skeleton validity rate*; (v) the *error taxonomy* over the five failure classes;
(vi) Critic action distribution and hallucinated lemma names; and (vii) cost, which is zero per
token but is reported as wall-clock and GPU time.

**Statistics.** Each solve rate is reported with a 95% Wilson score interval [@wilson1927], which
stays inside [0, 1] with small samples. Configurations are compared pairwise on the same problems
with the exact McNemar test [@mcnemar1947] on discordant pairs (two-sided binomial with p = 1/2),
with a Bonferroni correction [@dunn1961] over the 10 pairs (effective α = 0.005). Because with
n = 50 McNemar will probably not reach significance at that level, the study is declared
exploratory before the test set is opened, and each pairwise difference in solve rate is also
reported with a 95% percentile interval from a paired bootstrap [@efron1979] with 10,000
resamples and a fixed seed. All statistics are computed by a script over the JSONL logs.

## 4. Results

### 4.1 Infrastructure and component results (measured)

The following results were measured before the experiment and do not depend on the served prover:

- **Environment.** The D4 gate (`2 + 2 = 4` verified from Python) passes. All 244 miniF2F
  development statements compile with the pinned Mathlib.
- **Verifier.** The verdict classifier passes 13 of 13 cases on fabricated REPL responses and 8 of
  8 against the real kernel, including `SORRY`, `AXIOM` and `TIMEOUT`.
- **Graph.** The graph tests pass (7 of 7 for the configuration without retrieval and Critic at the
  time of the week 7–8 gate). A real development problem, `mathd_algebra_48`, went through the
  whole graph with scripted model responses and the real kernel deciding: the Planner split it
  into one step, the kernel accepted the skeleton, the step was proved as a standalone lemma,
  assembled, and the full theorem accepted:

```lean
theorem mathd_algebra_48 (q e : ℂ) (h₀ : q = 9 - 4 * Complex.I) (h₁ : e = -3 - 4 * Complex.I) :
  q - e = 12 := by
  have step1 : q - e = (9 - 4 * Complex.I) - (-3 - 4 * Complex.I) := by
    rw [h₀, h₁]
  rw [step1]
  ring
```

  The opposite case was also tested: a bad proof submitted twice, retry included, ends in
  `UNSOLVED_GOALS` and not in `SOLVED`.
- **Retriever.** recall@k = 0.173, 0.224, 0.287 and 0.362 for k = 5, 10, 20 and 50 over 179,269
  premises (Section 3.5).

### 4.2 Development runs (week 9)

| Measure (dev, 244 problems unless stated) | Value |
|---|---|
| Skeleton validity rate (`plan_only`) | [[RESULT: dev skeleton validity rate, x/244, Wilson 95% CI]] |
| Replans needed to obtain a valid skeleton | [[RESULT: dev fraction of valid skeletons that needed the one replan]] |
| Mean subgoals per valid skeleton | [[RESULT: dev mean (and median) subgoals per skeleton]] |
| Full system solve rate on dev | [[RESULT: dev solve rate full, x/n, Wilson 95% CI]] |
| Inside the 30–60% target band? | [[RESULT: yes/no; if no, what was changed on dev before freezing]] |
| *k* used after dev (default 10) | [[RESULT: final k chosen on dev, and whether NL-step queries were added]] |

[[RESULT: one paragraph on what was tuned on dev in week 9 and the prompt versions frozen in week
10, from the git history of prompts/]]

### 4.3 Main ablation on the sealed test set

Table 1. Solve rate on the 50-problem test set (opened once). Calls per solved problem refer to
LLM calls (the Verifier is not counted).

| # | Configuration | Solved / 50 | Solve rate | Wilson 95% CI | Calls per solved (mean) | Abandoned | `BUDGET_EXHAUSTED` |
|---|---|---|---|---|---|---|---|
| 1 | Baseline A | [[RESULT: baseline_a solved]] | [[RESULT: baseline_a rate]] | [[RESULT: baseline_a Wilson CI]] | [[RESULT: baseline_a calls/solved]] | n/a | n/a |
| 2 | Baseline B | [[RESULT: baseline_b solved]] | [[RESULT: baseline_b rate]] | [[RESULT: baseline_b Wilson CI]] | [[RESULT: baseline_b calls/solved]] | n/a | n/a |
| 3 | Agents only | [[RESULT: agents_only solved]] | [[RESULT: agents_only rate]] | [[RESULT: agents_only Wilson CI]] | [[RESULT: agents_only calls/solved]] | [[RESULT: agents_only abandoned]] | [[RESULT: agents_only budget exhausted]] |
| 4 | No Critic (RAG) | [[RESULT: no_critic solved]] | [[RESULT: no_critic rate]] | [[RESULT: no_critic Wilson CI]] | [[RESULT: no_critic calls/solved]] | [[RESULT: no_critic abandoned]] | [[RESULT: no_critic budget exhausted]] |
| 5 | Full system | [[RESULT: full solved]] | [[RESULT: full rate]] | [[RESULT: full Wilson CI]] | [[RESULT: full calls/solved]] | [[RESULT: full abandoned]] | [[RESULT: full budget exhausted]] |

External reference (not run by us): Goedel-Prover-V2-8B reports 84.6% pass@32 on miniF2F
[@lin2026goedel], with 32 samples per problem, a larger sampling budget and a different problem
set from our 50-problem subset; it is not comparable with Table 1 and is listed only to locate our
weakened single-pass baseline (D2). [[RESULT: optional — if run, baseline_a with the prover's
self-correction mode on the same 50 problems, clearly labeled as outside the ablation]]

Requirement RNF-3 (at most 20 calls per solved problem): [[RESULT: met / not met for full; max
calls observed on a solved problem; distribution of calls per solved problem]].

### 4.4 Pairwise comparisons

Table 2. Pairwise comparisons on the same 50 problems. *b* and *c* are discordant counts (solved
only by the first / only by the second). p-values are exact McNemar, two-sided; the Bonferroni
threshold is 0.005. Δ is the difference in solve rate (second minus first) with a paired bootstrap
95% interval (10,000 resamples).

| Pair | b | c | p (exact McNemar) | Significant at 0.005? | Δ solve rate | Bootstrap 95% CI |
|---|---|---|---|---|---|---|
| baseline_a vs full | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| baseline_b vs full | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| agents_only vs no_critic (effect of RAG) | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| no_critic vs full (effect of the Critic) | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| baseline_a vs agents_only (effect of decomposition) | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| remaining 5 pairs | see Appendix B | | | | | |

### 4.5 False positives avoided (baseline B)

| Measure | Value |
|---|---|
| Proofs the model declared correct (`self_verdict = correct`) | [[RESULT: baseline_b count self-declared correct, out of 50]] |
| ... of which the kernel accepted after formalization | [[RESULT: baseline_b count self-declared correct and kernel OK]] |
| ... of which the kernel rejected (false positives) | [[RESULT: baseline_b count self-declared correct and rejected]] |
| False-positive rate | [[RESULT: baseline_b FP rate with Wilson 95% CI]] |
| Proofs the model declared incorrect but the kernel accepted | [[RESULT: baseline_b count self-declared incorrect yet kernel OK]] |

Because baseline B's natural-language proof passes through one prover call before reaching the
kernel, a rejection can come from a wrong proof or from a failed translation. We therefore also
report [[RESULT: breakdown of baseline_b rejections by verdict: FORMALIZATION_FAILED vs kernel
verdicts]], and read the false-positive rate as an upper bound on the model's self-assessment
error.

### 4.6 Where the system fails

Table 3. Error taxonomy over failed attempts (all configurations with the graph), by the first
error Lean reports.

| Class | agents_only | no_critic | full |
|---|---|---|---|
| Syntax | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| Missing lemma | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| Unsolved goals | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| Timeout | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| Planning error (no valid skeleton, or assembly fails) | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| `FORMALIZATION_FAILED` | [[RESULT]] | [[RESULT]] | [[RESULT]] |
| `STATEMENT_CHANGED` | [[RESULT]] | [[RESULT]] | [[RESULT]] |

Additional measures:

- Skeleton validity rate on the test set: [[RESULT: test skeleton validity rate, x/50, Wilson CI]].
- Problems with every subgoal closed in isolation but failing `VERIFY_FINAL`: [[RESULT: count per
  configuration]].
- Hallucinated lemma names removed from sketches: [[RESULT: count per configuration; with vs
  without retrieval]].
- Critic actions in `full`: [[RESULT: distribution of RETRY_FORMALIZE / RETRIEVE_MORE /
  REGENERATE_SKETCH / REPLAN / ABANDON, and fraction of Critic outputs that failed validation and
  fell back to the verifier class]].
- Agreement between the Critic's class and the class implied by the verdict: [[RESULT: agreement
  rate]].

### 4.7 Cost

| Configuration | Wall-clock per problem (median) | Total GPU time | Prompt + completion tokens per problem (mean) | USD per token |
|---|---|---|---|---|
| baseline_a | [[RESULT]] | [[RESULT]] | [[RESULT]] | 0 |
| baseline_b | [[RESULT]] | [[RESULT]] | [[RESULT]] | 0 |
| agents_only | [[RESULT]] | [[RESULT]] | [[RESULT]] | 0 |
| no_critic | [[RESULT]] | [[RESULT]] | [[RESULT]] | 0 |
| full | [[RESULT]] | [[RESULT]] | [[RESULT]] | 0 |

## 5. Discussion

[[RESULT: the paragraphs in this section must be checked against Tables 1–3 once they exist;
each conditional below keeps only the branch the data supports.]]

**Does decomposition with a verified skeleton help?** The comparison between baseline A and
`agents_only` isolates decomposition, since both use the same prover and neither uses retrieval
or the Critic. The skeleton rate bounds what decomposition can achieve: a problem without a valid
skeleton cannot be solved by configurations 3–5. With a skeleton rate of [[RESULT: test skeleton
rate]], [[RESULT: interpretation — whether the 4B Planner was the bottleneck, i.e. whether
solve rate of agents_only is close to the skeleton rate or far below it]]. Our smoke test already
showed the characteristic failure of the small planner: a syntactically valid skeleton missing the
closing tactic. `VERIFY_SKELETON` turns that failure into an immediate, cheap rejection plus one
informed replan, instead of a series of subgoal proofs that could never be assembled into the
theorem. Independently of the final rates, this is the main qualitative argument for the design:
in a pipeline without the check, the same skeleton would have consumed most of the budget before
the failure became visible at assembly.

**Does retrieval help, given the low recall?** The retriever's recall@10 of 0.224 means that, on
average, fewer than a quarter of the premises a Mathlib proof uses appear among the ten retrieved.
That number is a pessimistic proxy for our use, for two reasons: the ground truth includes
premises inserted by tactics that a human would never cite, and a subgoal often needs one key
lemma, not all of them. The comparison `agents_only` vs `no_critic` measures the end effect
[[RESULT: Δ and bootstrap CI]], and the count of hallucinated names [[RESULT: with vs without
retrieval]] measures the mechanism that retrieval is supposed to affect. [[RESULT: interpretation
— if the effect is null or negative, discuss prompt-length cost and symbol-only queries; if
positive, discuss which error class decreased (Table 3, missing lemma)]].

**Does reading the error help?** The design of the `no_critic` configuration makes this
comparison specific: both configurations retry the same number of times, and the only difference
is whether the retry sees the raw Lean error and a diagnosis. The Critic's effect was therefore
not confounded with the prover's internal self-correction (D2) nor with an extra retry
[[RESULT: Δ no_critic → full with bootstrap CI and the McNemar p-value]]. [[RESULT:
interpretation — which actions the Critic chose most often and on which error classes the full
system recovered; whether the replan after VERIFY_FINAL ever produced a solve]].

**What self-assessment misses.** The false-positive measurement is, in our view, the result that
transfers most directly to how people use LLMs for mathematics. [[RESULT: x of y proofs the model
called correct were rejected by the kernel]]. Even allowing for translation failures, which make
the rate an upper bound, the size of this number is what justifies routing every success through a
verifier. It also matches the design premise stated at the outset: a model's confidence in its own
derivation is not a correctness signal.

**Budget.** The hard ceiling made the call budget a property of the system rather than a statistic
reported afterwards. [[RESULT: calls per solved problem for full vs the ceiling of 20, and how
often BUDGET_EXHAUSTED or the early cut-off ended a problem]]. A consequence worth stating is that
the budget interacts with the attempt cap: with two attempts per subgoal and *n* = 2 only on the
first, the budget binds only for problems with many subgoals [[RESULT: confirm with the
distribution of subgoals per skeleton]].

**Testing against the real kernel.** A finding that does not depend on the experiment is that
fabricated responses validated our assumptions rather than the system. All six bugs listed in
Section 3.10 passed every test that used scripted REPL responses, and at least two of them, the
empty environment and the misclassified Lean 3 syntax, would have produced false results silently:
the first would have made every proof fail for an unrelated reason, the second would have sent the
system to retrieve lemmas for syntax errors. For neuro-symbolic systems, we believe the symbolic
side should be exercised for real as early as possible, which is also why we moved the Lean
environment to week 1 (D4).

**Comparison with prior work.** Our absolute numbers are not comparable with Draft, Sketch, and
Prove, DeepSeek-Prover-V1.5 or Goedel-Prover-V2: we use a 4B planner instead of a frontier model,
one sample per formalization instead of dozens, a 20-call ceiling, and a 50-problem subset. The
claims that do transfer are the relative ones within the ablation, and the methodological ones:
verifying the skeleton, enforcing the budget, and measuring self-assessment against the kernel.

## 6. Ethical Considerations

The system is designed so that an AI tool never certifies its own work: a person or a kernel must.
This follows the principle articulated in MIT's 2026 report on AI use in teaching, learning and
research training, which asks that AI be viewed "as a tool under the direction of a human who is
responsible for verifying the accuracy of its output" and frames the goal as "augmentation not
automation" [@mit2026aicommittee]. In this project the requirement that only the kernel declares
success (RNF-1) is that principle turned into code. The system is meant to augment a person who
works on a problem, by proposing decompositions and candidate proofs, and its outputs are either
kernel-checked or explicitly marked as unverified. The false-positive measurement of Section 4.5
documents why: the model's own confidence would have certified wrong proofs.

Three further considerations apply. First, *data provenance*: miniF2F, its Lean 4 port and
PutnamBench keep their own licenses, documented in the dataset card; the problems come from public
competitions, and no personal data is involved. Second, *possible contamination*: public provers
may have been trained on data that overlaps with miniF2F; we cannot rule it out, and it is one more
reason to treat our results as relative comparisons within a fixed model set rather than as
measures of general ability. Third, *environmental and access cost*: running everything locally at
zero cost per token made the project feasible without funding, at the price of slower runs and
weaker models; we report wall-clock and GPU time so that the cost is visible.

Finally, this report itself was prepared with AI assistance. Following the model of the MIT
report's Appendix A, we declare that use in Appendix A below.

## 7. Limitations

1. **Weakened prover baseline (D2).** The prover is invoked in standard mode, one pass per
   formalization, with its compiler-guided self-correction disabled, so that every retry passes
   through our instrumented Critic and the ablation measures the Critic. Our baseline A is
   therefore weaker than the prover out of the box; the published self-correction numbers are an
   external reference only.
2. **Small local models.** Planning, sketching, critique and baseline B use a 4B instruction model,
   not a frontier model. Skeleton validity and solve rates are not comparable with systems that
   use API models. The ablation remains internally valid because every configuration uses the same
   models.
3. **Low recall on symbolic queries.** recall@10 is 0.224. Queries that are pure symbols retrieve
   poorly because the encoder relies on lemma names; we did not fine-tune the encoder or add
   queries from the Generator's natural-language step ([[RESULT: unless this was done on dev in
   week 9]]).
4. **Noisy retrieval ground truth.** Relevance is defined by the theorems appearing in a proof term
   extracted from the pinned commit, not by LeanDojo's annotations (which use a different commit).
   Proof terms include premises inserted by tactics, so recall@k underestimates usefulness.
5. **Statistical power.** With 50 test problems, ten pairwise comparisons and Bonferroni
   correction (α = 0.005), McNemar is unlikely to reach significance for moderate effects. The
   study is exploratory; we report Wilson and bootstrap intervals and effect sizes, and avoid
   significance claims the design cannot support.
6. **Single seed and single sample.** Each configuration was run once per problem with a fixed
   seed. The prover samples at temperature 0.6, so a rerun can change individual outcomes;
   variance across seeds is not estimated.
7. **Benchmark scope.** miniF2F is the only primary benchmark. PutnamBench, the secondary
   benchmark, was not ingested by week 8 because its statements include solution definitions that
   need separate handling ([[RESULT: final PutnamBench status]]). The test set covers 50 of the
   244 test problems.
8. **Statement check is syntactic.** `STATEMENT_CHANGED` compares statements textually. It prevents
   a model from proving an easier theorem, but a semantically equivalent rewording would also be
   rejected.
9. **Wall-clock limit binds before heartbeats.** The 120-second wall-clock limit always fires
   before the 400,000-heartbeat limit on our hardware, so `TIMEOUT` depends on the machine. Some
   problems solvable with more time are counted as failures.
10. **Hardware.** The prover does not fit in the local 4 GB GPU and is served externally; only 2–3
    Lean workers fit in 8 GB of memory. Results depend on the serving setup ([[RESULT: serving
    setup used]]).
11. **Self-set skeleton threshold.** The 70% skeleton-validity gate and the 30–60% target band are
    our own engineering choices, not values from the literature.
12. **Fabricated responses in tests.** Most graph tests use scripted model responses. The end-to-end
    test with the real kernel used scripted model responses, so until the week 11 runs, the claim
    that the graph works with real models rested on component tests.
13. **Schedule.** The D4 gate closed in week 3, not week 1, and the experiments depended on serving
    the prover, which was the last missing piece at the time of writing.
14. **Live demonstration.** Mounting Lean and Mathlib in a hosted demo is heavy (several gigabytes,
    slow start). The planned demo replays recorded traces and verifies only cached problems live.

## 8. Conclusion

We built a multi-agent system in which language models do the flexible part of mathematical
problem solving and the Lean 4 kernel does the part that cannot be argued with. The architecture
has three distinctive properties: the plan is a Lean skeleton that the kernel checks before any
subgoal is attempted; every model call is charged against a hard budget and logged; and the system
measures how often a model's own verdict on its proof is wrong. The infrastructure behind those
claims is in place and tested against the real kernel: 244 of 244 development statements compile,
the verifier distinguishes seven verdicts, a real problem goes through the whole graph and is
accepted by the kernel, and the retriever indexes 179,269 Mathlib premises with measured,
admittedly low, recall. On the sealed test set the full system solves [[RESULT: full solve rate
with Wilson CI]], against [[RESULT: baseline_a solve rate with Wilson CI]] for the single-call
prover, and the kernel rejects [[RESULT: baseline_b FP rate]] of the proofs the model declared
correct. [[RESULT: one sentence on the RAG and Critic effects with their bootstrap CIs]]. The main
lessons are that a small model's plans must be checked before they are trusted, that reading the
compiler's error is only measurable if the alternative retries just as often, and that a
neuro-symbolic system has to be tested against its symbolic side from the first week. Future work:
querying the retriever with the natural-language step as well as the type, a larger test set to
reach statistical power, PutnamBench, and the same architecture with a stronger planner to separate
the contribution of the architecture from the limits of a 4B model.

## References

Generated from `docs/references.bib` (keys in brackets).

- [vaswani2017attention] A. Vaswani et al. Attention is all you need. NeurIPS 30, 2017. arXiv:1706.03762.
- [brown2020language] T. B. Brown et al. Language models are few-shot learners. NeurIPS 33, 2020. arXiv:2005.14165.
- [ouyang2022training] L. Ouyang et al. Training language models to follow instructions with human feedback. NeurIPS 35, 2022. arXiv:2203.02155.
- [wei2022chain] J. Wei et al. Chain-of-thought prompting elicits reasoning in large language models. NeurIPS 35, 2022. arXiv:2201.11903.
- [wang2023selfconsistency] X. Wang et al. Self-consistency improves chain of thought reasoning in language models. ICLR, 2023. arXiv:2203.11171.
- [yao2023tree] S. Yao et al. Tree of thoughts: Deliberate problem solving with large language models. NeurIPS 36, 2023. arXiv:2305.10601.
- [hendrycks2021math] D. Hendrycks et al. Measuring mathematical problem solving with the MATH dataset. NeurIPS Datasets and Benchmarks, 2021. arXiv:2103.03874.
- [yao2023react] S. Yao et al. ReAct: Synergizing reasoning and acting in language models. ICLR, 2023. arXiv:2210.03629.
- [shinn2023reflexion] N. Shinn et al. Reflexion: Language agents with verbal reinforcement learning. NeurIPS 36, 2023. arXiv:2303.11366.
- [wu2024autogen] Q. Wu et al. AutoGen: Enabling next-gen LLM applications via multi-agent conversation. COLM, 2024. arXiv:2308.08155.
- [park2023generative] J. S. Park et al. Generative agents: Interactive simulacra of human behavior. UIST, 2023. doi:10.1145/3586183.3606763.
- [lewis2020rag] P. Lewis et al. Retrieval-augmented generation for knowledge-intensive NLP tasks. NeurIPS 33, pp. 9459–9474, 2020. arXiv:2005.11401.
- [karpukhin2020dpr] V. Karpukhin et al. Dense passage retrieval for open-domain question answering. EMNLP, pp. 6769–6781, 2020. doi:10.18653/v1/2020.emnlp-main.550.
- [chen2024m3] J. Chen et al. M3-Embedding: Multi-linguality, multi-functionality, multi-granularity text embeddings through self-knowledge distillation. Findings of ACL, pp. 2318–2335, 2024. doi:10.18653/v1/2024.findings-acl.137.
- [wang2022e5] L. Wang et al. Text embeddings by weakly-supervised contrastive pre-training. arXiv:2212.03533, 2022.
- [johnson2021faiss] J. Johnson, M. Douze, H. Jégou. Billion-scale similarity search with GPUs. IEEE Trans. Big Data 7(3):535–547, 2021. doi:10.1109/TBDATA.2019.2921572.
- [demoura2021lean4] L. de Moura, S. Ullrich. The Lean 4 theorem prover and programming language. CADE-28, LNCS 12699, pp. 625–635, 2021. doi:10.1007/978-3-030-79876-5_37.
- [mathlib2020] The mathlib Community. The Lean mathematical library. CPP, pp. 367–381, 2020. doi:10.1145/3372885.3373824.
- [polu2020generative] S. Polu, I. Sutskever. Generative language modeling for automated theorem proving. arXiv:2009.03393, 2020.
- [wu2022autoformalization] Y. Wu et al. Autoformalization with large language models. NeurIPS 35, 2022. arXiv:2205.12615.
- [jiang2023dsp] A. Q. Jiang et al. Draft, sketch, and prove: Guiding formal theorem provers with informal proofs. ICLR, 2023. arXiv:2210.12283.
- [yang2023leandojo] K. Yang et al. LeanDojo: Theorem proving with retrieval-augmented language models. NeurIPS Datasets and Benchmarks, 2023. arXiv:2306.15626.
- [first2023baldur] E. First, M. N. Rabe, T. Ringer, Y. Brun. Baldur: Whole-proof generation and repair with large language models. ESEC/FSE, pp. 1229–1241, 2023. doi:10.1145/3611643.3616243.
- [xin2025deepseekprover] H. Xin et al. DeepSeek-Prover-V1.5: Harnessing proof assistant feedback for reinforcement learning and Monte-Carlo tree search. ICLR, 2025. arXiv:2408.08152.
- [lin2026goedel] Y. Lin et al. Goedel-Prover-V2: Scaling formal theorem proving with scaffolded data synthesis and self-correction. ICLR, 2026. arXiv:2508.03613.
- [zheng2022minif2f] K. Zheng, J. M. Han, S. Polu. miniF2F: a cross-system benchmark for formal Olympiad-level mathematics. ICLR, 2022. arXiv:2109.00110.
- [tsoukalas2024putnambench] G. Tsoukalas et al. PutnamBench: Evaluating neural theorem-provers on the Putnam mathematical competition. NeurIPS Datasets and Benchmarks, 2024. arXiv:2407.11214.
- [trinh2024alphageometry] T. H. Trinh, Y. Wu, Q. V. Le, H. He, T. Luong. Solving olympiad geometry without human demonstrations. Nature 625:476–482, 2024. doi:10.1038/s41586-023-06747-5.
- [mit2026aicommittee] MIT Ad Hoc Committee on AI Use in Teaching, Learning, and Research Training. Report of MIT's Ad Hoc Committee on AI Use in Teaching, Learning, and Research Training. Massachusetts Institute of Technology, August 13, 2026.
- [yang2025qwen3] A. Yang et al. Qwen3 technical report. arXiv:2505.09388, 2025.
- [ollama] Ollama. Software, https://ollama.com.
- [langgraph] LangChain, Inc. LangGraph. Software, https://github.com/langchain-ai/langgraph.
- [leanrepl] leanprover-community. REPL for Lean 4. Software, https://github.com/leanprover-community/repl.
- [kwon2023vllm] W. Kwon et al. Efficient memory management for large language model serving with PagedAttention. SOSP, pp. 611–626, 2023. doi:10.1145/3600006.3613165.
- [wilson1927] E. B. Wilson. Probable inference, the law of succession, and statistical inference. J. Amer. Statist. Assoc. 22(158):209–212, 1927. doi:10.1080/01621459.1927.10502953.
- [mcnemar1947] Q. McNemar. Note on the sampling error of the difference between correlated proportions or percentages. Psychometrika 12(2):153–157, 1947. doi:10.1007/BF02295996.
- [dunn1961] O. J. Dunn. Multiple comparisons among means. J. Amer. Statist. Assoc. 56(293):52–64, 1961. doi:10.1080/01621459.1961.10482090.
- [efron1979] B. Efron. Bootstrap methods: Another look at the jackknife. Ann. Statist. 7(1):1–26, 1979. doi:10.1214/aos/1176344552.

## Appendix A. Declaration of AI use

[[AUTHORS: complete and confirm this declaration; it must describe what was actually done.]]

- Code: [[AUTHORS: which parts of the code were written or reviewed with AI assistance]].
- This report: an AI assistant (Claude, Anthropic) was used to draft the structure and the text
  of this report from the project's internal documents (`docs/decisions.md`,
  `docs/design-document.md`, `docs/status.md`, `docs/related-work.md`), and to audit the
  bibliography against arXiv, Crossref and the publishers' pages. The authors reviewed and are
  responsible for every statement. No experimental number was produced or estimated by an AI
  assistant: all results come from aggregating the run logs.
- The agents of the system itself are AI models (Section 3.9); that use is the object of study,
  not assistance.

## Appendix B. Remaining pairwise comparisons and reproduction

[[RESULT: remaining 5 pairwise comparisons table from `python -m src.analysis`]]

Reproduction (inside the Docker image, with Ollama on the host and `PROVER_URL` set):

```bash
python -m src.data                                   # miniF2F, checked by SHA-256
python -m src.retriever build                        # FAISS index over 179,269 premises
python run.py --config plan_only                     # skeleton rate on dev
python run.py --config full --problems "$(python -m src.data --test-set-ids)" --split test --abrir-test
python -m src.analysis runs/*.jsonl --out results/   # Wilson, McNemar, bootstrap
```
