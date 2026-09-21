# Estado del proyecto

Actualizado: 2026-09-20 · Semanas 1–2 cerradas.

## Criterio de "hecho" de las semanas 1–2

> El documento de diseño está completo, los schemas validan, y `verify()` distingue
> correctamente los veredictos sobre casos de prueba fabricados a mano.

| Condición | Estado | Evidencia |
|---|---|---|
| Documento de diseño completo | ✅ | `docs/design-document.md` |
| ≥15 referencias primarias por eje | ✅ 27 | `docs/related-work.md` |
| Seis JSON Schema validan | ✅ 6/6 draft 2020-12 | `docs/contracts/` |
| `verify()` distingue los veredictos | ✅ 12/12 | `python tests/test_verify.py` |
| Prompts v0 versionados como archivos | ✅ 4/4 | `prompts/*.v0.md` |
| Grafo de estados con `VERIFY_SKELETON` y `ASSEMBLE` | ✅ | `docs/design-document.md` §3 |
| Formalización del retriever (§6.4) | ✅ | `docs/design-document.md` §4 |
| **Compuerta D4: `2 + 2 = 4` desde Python** | ⏳ **PENDIENTE** | requiere ejecutar el build de Docker |

## Lo único que bloquea

**`docker build -t mathagents-lean:v4.15.0 lean/`** no se ha ejecutado. Es la compuerta del día
5 de la semana 1 y el riesgo técnico más alto del proyecto (D4). Todo lo demás está escrito
contra un `Repl` inyectable y probado con respuestas fabricadas, así que el build es lo único
que falta para cerrar de verdad.

Dos cosas se resuelven al correrlo y hasta entonces son **supuestos, no hechos**:

1. **El par toolchain/Mathlib.** `lean-toolchain` dice `v4.15.0` y el `lakefile.lean` pide el tag
   `v4.15.0` de mathlib4. Si ese tag no existe o no casa con el toolchain, `lake exe cache get`
   falla o compila desde fuente (horas). Ajustar ambos al mismo valor y volver a construir.
2. **El commit exacto de Mathlib.** El build lo escribe en `/app/mathlib-commit.txt`. Copiarlo a
   `decisions.md` D1.3: es el número que se cita en el informe (RNF-2) y no debe inventarse.

El formato de mensajes del REPL (`messages` con `severity`, `sorries`, `env`) y el texto de
`#print axioms` están tomados del protocolo documentado, pero **conviene volcar una respuesta
real a `tests/fixtures/` en cuanto la imagen exista** y comparar contra lo que asumen los tests.

## Reparto y compuertas siguientes

| Semana | Entregable | Compuerta |
|---|---|---|
| 3–4 | Líneas base A y B, runner `run.py`, ingesta miniF2F/PutnamBench | ambas líneas base corren sobre dev end-to-end, JSONL válido, costo por problema en dólares |
| 5–6 | Planificador con esqueleto + Generador, corpus y FAISS | esqueletos compilan en >70% de dev; curva recall@k para k ∈ {5,10,20} |
| 7–8 | Autoformalizador, `ASSEMBLE`, pool de REPLs, CI | un problema entra y sale veredicto del kernel, sin RAG ni Crítico |
| 9 | RAG + Crítico | las 5 configuraciones son invocables por bandera |
| 10 | Test set 40–60, dataset card | prompts CONGELADOS |
| 11 | Experimentos | el test set se abre **una sola vez** |
| 12 | Análisis y empaquetado | Wilson, McNemar, bootstrap; repo HF |
| 13 | Informe IMRaD + sustentación | ~8.000 palabras |

**Puntos de integración obligatorios:** fin de semana 2 (verificador ↔ contratos) ✅ · fin de
semana 4 (dataset ↔ runner) · fin de semana 9 (RAG ↔ grafo).

**Punto de corte:** si el pipeline end-to-end no corre al final de la semana 8, el RAG se recorta
a extensión declarada y la ablación corre con 4 configuraciones.

## Deuda declarada

- `docs/references.bib` no existe. Las 27 entradas de `related-work.md` están escritas de
  memoria: hay que auditar venue, año y DOI contra la fuente antes de citarlas.
- Referencia del informe del MIT sin identificar (`related-work.md` eje 7).
- `decisions.md` D2 afirma que Goedel-Prover-V2 permite desactivar la autocorrección interna.
  **Verificarlo en el paper y en el código del modelo antes de la semana 7.** Si no se puede
  desactivar, hay que pasar a la opción (b) y declararlo como parte de la línea base.
