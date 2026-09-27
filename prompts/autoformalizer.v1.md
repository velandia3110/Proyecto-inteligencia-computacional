---
agent: autoformalizer
version: v1
model: Goedel-Prover-V2-8B
temperature: 0.6
self_correction: DISABLED
contract: docs/contracts/autoformalizer.schema.json (lo arma el codigo, no el modelo)
---

> Cambio respecto a v0: v0 pedia JSON a un modelo de instrucciones, pero Goedel-Prover-V2
> es un prover entrenado con un formato fijo y no devuelve JSON confiable. Aqui se le da
> el subobjetivo como un lema suelto (hipotesis del teorema + `have` previos) con el
> boceto como comentario. El codigo saca las tacticas del bloque lean4 y arma el JSON del
> contrato. Sigue sin autocorreccion interna (D2): el error de Lean solo entra por el
> bloque de reintento, que lo arma el Critico (semana 9).

# System

# User

Complete the following Lean 4 code:

```lean4
{header}
/-- Proof sketch:
{sketch_steps}
Suggested tactics: {tactic_hints}
Useful lemmas: {retrieved_lemmas} -/
{subgoal_lemma} := by
  sorry
```
{retry_block}
Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.
The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof.

---

## Bloque de reintento (RF-6, lo llena el Critico en la semana 9)

```
The previous attempt failed.

Previous proof:
{previous_proof}

Lean error (verbatim):
{lean_error}

Diagnosis: {diagnosis}
```
