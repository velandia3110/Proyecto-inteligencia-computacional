---
agent: baseline_b_formalize
version: v0
model: Goedel-Prover-V2-8B
temperature: 0.6
contract: ninguno (salida de texto; el runner extrae el bloque lean4)
---

> Formaliza la prueba en lenguaje natural de la linea base B, una sola llamada.
> No es parte de lo que "resuelve" B: solo sirve para medir cuantas de las pruebas
> que B dio por correctas el kernel acepta.

# System

# User

Complete the following Lean 4 code, following the natural-language proof given in the comment:

```lean4
{header}
/-- {nl_statement}

Proof: {nl_proof} -/
{formal_statement} := by
  sorry
```

Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.
The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof.
