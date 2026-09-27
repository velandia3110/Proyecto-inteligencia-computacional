---
agent: baseline_a
version: v0
model: Goedel-Prover-V2-8B
temperature: 0.6
contract: ninguno (salida de texto; el runner extrae el bloque lean4)
---

> Linea base A (§8.2 config 1): un solo prompt, una sola llamada, prueba completa.
> Es el formato con el que se entreno Goedel-Prover-V2, sin cambios, para que la
> comparacion sea contra el prover "tal cual" y no contra un prompt nuestro peor.

# System

# User

Complete the following Lean 4 code:

```lean4
{header}
/-- {nl_statement} -/
{formal_statement} := by
  sorry
```

Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.
The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof.
