# Decisiones congeladas

Estado: **CONGELADO** desde el día 1 de la semana 1.
Cambiar cualquier fila cuesta semanas. Cambio → nueva fila en *Historial*, nunca edición silenciosa.

## D1 — Stack

| # | Decisión | Elección | Justificación |
|---|---|---|---|
| D1.1 | Orquestador | **LangGraph** | Estado tipado + checkpoints. El grafo es un entregable visible (15% arquitectura); CrewAI lo oculta tras roles. |
| D1.2 | Interfaz Lean | `leanprover-community/repl` (cliente JSON propio, ver nota) | LeanDojo exige crear/tracear un repo Lean por interacción; el REPL acepta código suelto y permite sesiones vivas. |
| D1.3 | Mathlib | Commit **fijo** `9837ca9d65d9de6fad1ef4381750ca688774e608` (tag v4.15.0) + `lake exe cache get` en el build de Docker | Compilar Mathlib desde fuente son horas de CPU por imagen. El hash sale de `/app/mathlib-commit.txt`, no se escribió a mano. |
| D1.4 | LLM planificación/crítica | Modelo de frontera vía API (`claude-opus-5`) | 1–2 llamadas por problema; el costo marginal es irrelevante frente a la calidad del plan. |
| D1.5 | LLM formalización | **Goedel-Prover-V2-8B** (Apache-2.0) | Es el volumen de llamadas. 84.6% pass@32 en miniF2F siendo ~80× menor que DeepSeek-Prover-V2-671B. Self-hosted = costo marginal ≈ 0. |
| D1.6 | Embeddings | **BGE-M3** + FAISS `IndexFlatIP` | Local, sin costo por llamada. Vectores L2-normalizados ⇒ producto interno = coseno (ver `docs/design-document.md` §4). |
| D1.7 | Benchmark | **miniF2F** primario, **PutnamBench** secundario | Enunciados ya formalizados y auditados: elimina el riesgo de mal-formalización del enunciado. |
| D1.8 | Lenguaje del informe | Inglés, IMRaD | Requisito del curso. Los documentos internos (`docs/`) van en español. |

**Nota sobre D1.2.** LeanInteract es un envoltorio *sobre el mismo* `leanprover-community/repl`;
su valor añadido es gestionar el proyecto Lean y la toolchain, que aquí ya resuelve el Dockerfile.
Se habla con el REPL directamente desde `src/lean_repl.py` (~120 líneas, solo stdlib) por dos
razones: el protocolo JSON es estable y no introduce deriva de versión de una dependencia
intermedia, y en la semana 7 hace falta un **pool de procesos REPL reutilizables**, que exige
control sobre el ciclo de vida del proceso. Si el cliente propio da problemas, `lean-interact` se
instala y se sustituye la implementación de `LeanRepl.run`: el resto del sistema solo depende de
esa firma.

## D2 — Solapamiento Crítico ↔ self-correction del prover

**Problema.** Goedel-Prover-V2 incorpora autocorrección guiada por el compilador de Lean. Es
exactamente la función del agente Crítico. Si se deja activa, la ablación *sin Crítico* compara
"Crítico externo + autocorrección interna" contra "autocorrección interna", y el efecto medido
no es el del Crítico.

**Elección: (a) — prover en modo estándar, sin self-correction interno.**

- Se invoca el prover en un solo paso (`max_correction_rounds = 0`): recibe boceto + lemas,
  devuelve tácticas, no ve el error del compilador por su cuenta.
- Todo ciclo de reintento pasa por el agente Crítico, que es código nuestro y queda instrumentado
  en el JSONL.
- Consecuencia honesta: nuestra línea base es más débil que el prover "de fábrica". Se declara en
  *Limitations* y se reporta el número del prover con autocorrección como referencia externa.

Alternativa descartada: (b) declarar la autocorrección interna como parte de la línea base. Se
descarta porque haría inauditable el conteo de llamadas del RNF-3.

## D3 — Presupuesto de llamadas (RNF-3: ≤20 por problema **resuelto**)

Costo por problema del sistema completo:

```
plan(1) + VERIFY_SKELETON(0) + Σ_subobjetivos [ generate(n) + formalize(1) + critique(≤1) ] × intentos
```

Peor caso ingenuo con 5 subobjetivos, n=2, k_max=3: ~60 llamadas. Tres reglas lo bajan al techo:

1. **n=2 solo en el primer intento**, n=1 en reintentos (self-consistency donde paga).
2. **Corte temprano**: si el Crítico clasifica el error como irrecuperable (`PLANNING_ERROR`
   tras replanificar una vez, o `TIMEOUT` repetido), se abandona el subobjetivo.
3. El requisito se mide sobre **problemas resueltos**, que es lo que dice literalmente. Los
   abandonados se reportan aparte.

**Implementación.** Objeto `Budget` (`src/budget.py`) con techo duro `max_llm_calls=20`. Al
excederlo aborta la corrida y registra veredicto `BUDGET_EXHAUSTED`. No es un aviso: es un
`raise`. Sin esto el RNF-3 es una aspiración, no un requisito.

## D4 — Adelanto del entorno Lean a la semana 1

El cronograma oficial pone el entorno Lean en la semana 3. Se adelanta a la semana 1 sin tocar
ningún entregable: es el riesgo técnico más alto del proyecto (toolchain + Mathlib + REPL +
puente Python) y es el único que puede invalidar el alcance completo.

**Compuerta del día 5 de la semana 1:** `theorem test : 2 + 2 = 4 := by norm_num` verificado
desde Python. Si el viernes no corre, se para y se renegocia el alcance con el docente.

Se justifica en la sección *Methodology* del informe.

## D5 — Reglas transversales

1. El **test set se abre una sola vez**, en la semana 11. Todo el ajuste va sobre dev.
2. **Prompts como archivos versionados** en `prompts/`. Cero strings de prompt en el código.
3. **Ninguna métrica se calcula a mano.** Todo sale de agregar `runs/*.jsonl`.
4. **Prompts congelados** desde la semana 10. Tocar un prompt con el test abierto invalida el
   20% de diseño experimental.
5. **Punto de corte:** si el pipeline end-to-end no corre al final de la semana 8, el RAG se
   recorta a extensión declarada y la ablación corre con 4 configuraciones.

## Historial de cambios

| Fecha | Decisión | Cambio | Motivo |
|---|---|---|---|
| 2026-09-20 | — | Congelado inicial | — |
| 2026-09-27 | D1.2 | El REPL se clona en el tag `v4.15.0` y se lanza con `lake env` | El master del REPL va con un Lean más nuevo, y sin `lake env` el REPL no encontraba ni el prelude, el `import Mathlib` pasaba callado sin cargar nada. Salió al correr la compuerta D4. |
| 2026-09-27 | D1.4 | Sin `temperature` en las llamadas a claude-opus-5 | El modelo ya no acepta ese parámetro (da error 400). Las temperaturas de los prompts v0 quedan como dato histórico, la variedad entre bocetos del Generador sale del muestreo normal del modelo. |
| 2026-09-27 | D1.5 | Autoformalizador pasa a `prompts/autoformalizer.v1.md` con el formato de entrenamiento de Goedel-Prover | El v0 le pedía JSON a un prover que no fue entrenado para eso. Ahora el subobjetivo va como lema suelto y el JSON del contrato lo arma el código. |
| 2026-09-27 | §8.2 | La línea base A usa Goedel-Prover (el mismo formalizador del sistema), una llamada, prueba completa | Así la comparación contra el sistema mide la arquitectura y no un cambio de modelo. |
| 2026-09-27 | datos | `maxHeartbeats 400000` en vez de `0` en el encabezado de miniF2F | Con 0 un `simp` que no termina cuelga el proceso en vez de dar `TIMEOUT`. |
| 2026-09-27 | §8.2 config 3 | Sin Crítico, un subobjetivo que falla se reintenta **a ciegas** (bocetos nuevos, sin ver el error de Lean), máximo 2 intentos por subobjetivo | Si la config sin Crítico no reintentara nada, la ablación mediría "reintentar vs no reintentar" y no lo que aporta leer el error. Así la única diferencia con el sistema completo es el Crítico. |
| 2026-09-27 | D2 | Verificado: la autocorrección de Goedel-Prover-V2 es un ciclo afuera del modelo (se le vuelve a pasar el error del compilador), en una sola llamada ya está apagada | README oficial del modelo, distingue "standard mode" y "self-correction mode". Se queda la opción (a). |
| 2026-09-27 | §4 | Verdad de referencia del recall@k = teoremas que aparecen en el término de prueba, sacados del mismo commit de Mathlib, en vez de las anotaciones de LeanDojo | LeanDojo va con otro commit de Mathlib y los nombres no casan. El término de prueba es más ruidoso (trae lo que las tácticas meten por dentro), se declara en *Limitations*. |
