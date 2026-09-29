# Estado del proyecto

Actualizado: 2026-09-28 · Semanas 1–8 cerradas en lo que depende de nosotros. Planificador, Generador y Crítico pasaron a un modelo local con Ollama (`qwen3:4b-instruct`, costo 0); lo que falta es la corrida sobre dev y el prover servido.

## Semanas 1–2

| Condición | Estado | Evidencia |
|---|---|---|
| Documento de diseño completo | ✅ | `docs/design-document.md` |
| ≥15 referencias primarias por eje | ✅ 27 | `docs/related-work.md` |
| Seis JSON Schema validan | ✅ 6/6 draft 2020-12 | `docs/contracts/` |
| `verify()` distingue los veredictos | ✅ 13/13 fabricados, 8/8 contra el kernel real | `tests/test_verify.py`, `tests/test_kernel.py` |
| Prompts v0 versionados como archivos | ✅ | `prompts/*.v0.md` |
| **Compuerta D4: `2 + 2 = 4` desde Python** | ✅ | `python3 -m src.verify --smoke` → `veredicto=OK axiomas=['propext']` |

La compuerta D4 se cerró tarde, en la semana 3, y no salió a la primera, salieron dos errores que con respuestas fabricadas nunca se hubieran visto. El primero fue que el REPL corría sin `lake env` y no encontraba ni el prelude de Lean, lo raro es que el `import Mathlib` no se quejaba, simplemente no cargaba nada, y todo lo demás fallaba con "unknown constant 'OfNat'". El segundo fue que el REPL no entiende los caracteres Unicode escapados como pares sustitutos en el JSON, entonces cualquier enunciado con `𝓝` daba error de sintaxis. Ahí también se vio que la sintaxis de Lean 3 (`begin ... end`) sale como "unknown identifier 'begin'" y el clasificador la tomaba como lema faltante, lo cual habría mandado al sistema a buscar más lemas cuando el problema era de sintaxis, eso ya quedó corregido y con su caso de prueba.

## Semanas 3–4: líneas base, runner e ingesta

Compuerta: ambas líneas base corren sobre dev de punta a punta, JSONL válido y costo por problema en dólares.

| Condición | Estado | Evidencia |
|---|---|---|
| Ingesta de miniF2F | ✅ 244 dev / 244 test | `python -m src.data`, fuente fijada por sha256 |
| Los 244 enunciados de dev compilan con nuestra Mathlib | ✅ 244/244 | `python3 -m src.data --check valid` (en Docker) |
| Línea base A (prover, una llamada) | ✅ código · ⏳ corrida | `src/baselines.py`, prueba de punta a punta con el kernel real en `tests/test_kernel.py` |
| Línea base B (CoT + autoevaluación, luego se formaliza) | ✅ código · ⏳ corrida | `src/baselines.py`, `tests/test_pipeline.py` |
| Runner con JSONL y encabezado reproducible | ✅ | `run.py`, `src/runlog.py` |
| Costo por problema en dólares | ✅ se calcula del JSONL | `python -m src.runlog runs/<id>.jsonl` |
| Test set sellado | ✅ | el runner no abre `--split test` sin `--abrir-test` |
| PutnamBench | ❌ no se hizo | ver deuda |

Lo que se hizo en estas dos semanas fue dejar toda la tubería por la que pasa cualquier configuración, el runner carga el problema, arma un contexto con su propio presupuesto, corre la configuración y escribe una línea por cada llamada al LLM y una línea de resultado por problema, y las métricas salen de agregar ese archivo y no de contar a mano. El encabezado del log guarda el commit de Mathlib y del repositorio que se leen de verdad, no escritos a mano.

Hay un chequeo que no estaba en el diseño y que resultó importante, antes de mandar una prueba al kernel se revisa que el enunciado del teorema siga igual al original. Sin eso un modelo puede probar un teorema más fácil que compila limpio y contaría como resuelto, esos casos quedan con veredicto `STATEMENT_CHANGED` y ni siquiera se le preguntan al kernel.

La línea base B guarda lo que el modelo dijo de su propia prueba (`self_verdict`) y después la formaliza con una llamada al prover, así se puede contar cuántas veces el modelo dijo "correcta" y el kernel dijo que no, que es el dato de falsos positivos evitados que va en el abstract.

**Lo que falta para cerrar la compuerta de verdad** es correr las dos líneas base sobre dev, y eso necesita Ollama corriendo con `qwen3:4b-instruct` (ya no hace falta clave de API) y el prover servido en algún lado. Goedel-Prover-V2-8B no cabe en la GPU de acá (4 GB), la idea es levantarlo con vLLM en Colab o en un endpoint de HF y pasar `PROVER_URL`. Con eso:

```bash
docker run --rm -v "$PWD:/work" -w /work --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 -e PROVER_URL \
  mathagents-lean:v4.15.0 python3 run.py --config baseline_a
```

## Semanas 5–6: planificador, generador y recuperador

Compuerta: los esqueletos compilan en más del 70% de dev, y hay curva recall@k para k ∈ {5, 10, 20}.

| Condición | Estado | Evidencia |
|---|---|---|
| Planificador con esqueleto y `VERIFY_SKELETON` | ✅ código · ⏳ tasa en dev | `src/agents.py`, config `plan_only` |
| Generador con n bocetos y voto | ✅ | `src/agents.py`, `tests/test_pipeline.py` |
| Corpus de premisas del mismo commit de Mathlib | ✅ 252.002 teoremas, 179.269 tras quitar autogenerados | `lean/Extract.lean`, 23 min en Docker |
| Índice FAISS exacto sobre BGE-M3 | ✅ 179.269 × 1024, normalizado | `python -m src.retriever build`, ~34 min en la GPU de 4 GB |
| Curva recall@k | ✅ ver tabla | `python -m src.retriever recall 5 10 20 50` |
| Esqueletos compilan en >70% de dev | ⏳ | falta la corrida con Ollama; en la prueba de humo el esqueleto de qwen3:4b-instruct no traía la táctica final |

El planificador no entrega una lista en prosa sino un teorema en Lean con un `have ... := by sorry` por paso, y antes de seguir se revisan tres cosas: que no haya cambiado el enunciado, que cada subobjetivo esté de verdad en el esqueleto y que no haya `sorry` escondidos en otra parte (por ejemplo en la táctica final, que haría trampa). Después el kernel lo compila con los `sorry` permitidos y si pasa, los pasos implican el teorema. Si algo falla se replanifica una sola vez con el error pegado en el prompt. Un detalle que salió al escribirlo es que el enunciado de cada paso se toma del texto del esqueleto y no del JSON, porque es el esqueleto lo que el kernel revisó y los dos podían no coincidir.

En el generador, cuando el modelo cita un lema que no estaba en la lista que se le dio, ese nombre se quita y queda anotado en el log como evento, así se puede contar después cuántas alucinaciones de nombres hubo sin que eso infle el conteo de llamadas.

**Recall@k** sobre 1.000 teoremas de Mathlib al azar (semilla 0). La consulta es el tipo del teorema y lo relevante son los teoremas que aparecen en su prueba.

| k | 5 | 10 | 20 | 50 |
|---|---|---|---|---|
| recall@k | 0,173 | 0,224 | 0,287 | 0,362 |

Los números son bajos, y conviene decirlo tal cual. En una prueba a mano se vio de dónde sale buena parte del problema: si la consulta trae un nombre (`Nat.Prime p → 2 ≤ p`) el lema exacto sale primero con 0,85, pero si la consulta es puro símbolo (`0 ≤ x ^ 2`, `a * b = 0 → a = 0 ∨ b = 0`) los lemas obvios como `sq_nonneg` o `mul_eq_zero` ni siquiera salen en el top 5. Como el texto indexado empieza por el nombre del lema, el codificador se apoya mucho en los nombres. Además la verdad de referencia es ruidosa, porque el término de prueba trae también lo que las tácticas meten por dentro y que nadie escribiría a mano. Con esta curva el k razonable está entre 10 y 20, el costo es solo largo de prompt, y la decisión final se toma en la semana 9 viendo si el RAG sube la tasa de resolución, que es lo que importa. Una mejora barata para probar ahí es consultar con el paso en lenguaje natural del generador además del tipo.

## Semanas 7–8: autoformalizador, ensamblado, pool de REPLs y CI

Compuerta: un problema entra y sale veredicto del kernel, sin RAG ni Crítico.

| Condición | Estado | Evidencia |
|---|---|---|
| Autoformalizador con Goedel-Prover, sin autocorrección (D2) | ✅ | `src/agents.py`, `prompts/autoformalizer.v1.md` |
| Grafo completo en LangGraph (config `agents_only`) | ✅ | `src/graph.py`, 7/7 en `tests/test_graph.py` |
| `ASSEMBLE` + `VERIFY_FINAL` | ✅ | `src/lean_text.py`, solo `VERIFY_FINAL` da SOLVED |
| **Compuerta: un problema entra y sale veredicto del kernel** | ✅ con LLM falso | `tests/test_kernel.py`: `mathd_algebra_48` resuelto por el kernel real |
| Pool de REPLs y `--workers` | ✅ | `src/repl_pool.py`, `tests/test_kernel_pool.py` |
| `TIMEOUT` contra el kernel real | ✅ | `tests/test_kernel_pool.py` |
| CI | ✅ | `.github/workflows/ci.yml` |
| Corrida con LLM de verdad | ⏳ | Ollama listo, falta el prover servido |

La compuerta se cerró pasando un problema real de dev por todo el grafo, con respuestas del LLM puestas a mano pero con el kernel de verdad decidiendo. El planificador parte `mathd_algebra_48` en un paso, el kernel acepta el esqueleto con su `sorry`, el paso se prueba como lema suelto, se pega en el esqueleto y el kernel acepta el teorema completo:

```lean
theorem mathd_algebra_48 (q e : ℂ) (h₀ : q = 9 - 4 * Complex.I) (h₁ : e = -3 - 4 * Complex.I) :
  q - e = 12 := by
  have step1 : q - e = (9 - 4 * Complex.I) - (-3 - 4 * Complex.I) := by
    rw [h₀, h₁]
  rw [step1]
  ring
```

También está el caso contrario, una prueba mala dos veces seguidas (con el reintento incluido) termina en `UNSOLVED_GOALS` y no en resuelto. Lo que falta para que la compuerta cuente con modelos de verdad es lo mismo de siempre, la clave y el prover, pero el camino por el que pasa un problema ya está probado de punta a punta.

Sin Crítico, cuando un paso falla se vuelve a intentar a ciegas, con bocetos nuevos pero sin mostrarle al modelo el error de Lean, y máximo dos intentos por paso. Se hizo así para que la ablación de la semana 9 mida lo que aporta leer el error y no lo que aporta simplemente volver a intentar (ver `decisions.md`).

Probando el pool contra Lean real salieron dos errores más que con respuestas fabricadas no se veían. El primero, cuando Lean se muere por desbordamiento de pila (pasa con `decide` y un `maxRecDepth` alto) el REPL no responde nada y eso se estaba contando como error de sintaxis, ahora cuenta como `TIMEOUT` y el REPL se vuelve a levantar solo. El segundo, `lake env` lanza el REPL como proceso hijo, entonces al cortar por timeout se mataba a `lake` pero el REPL seguía vivo por debajo gastando CPU y hasta 3 GB de memoria, ahora se mata el grupo entero de procesos. Cada REPL comparte con los otros los ~3,9 GB de Mathlib mapeados desde disco y lo propio de cada uno son unos 0,3–0,4 GB, entonces con los 8 GB de Docker caben 2 o 3 trabajadores.

Hay un dato sobre el límite de heartbeats que sirve para la semana 11: en esta máquina Lean gasta unos 20.000 heartbeats cada 7 a 12 segundos, entonces los 400.000 del encabezado tardan varios minutos y en la práctica el que corta siempre es el límite de 120 s de reloj.

El CI corre en cada push las pruebas que no necesitan Lean ni modelos, y las del kernel real se lanzan a mano porque construir la imagen toma unos 20 minutos y varios GB.

## Reparto y compuertas siguientes

| Semana | Entregable | Compuerta |
|---|---|---|
| 9 | RAG + Crítico | las 5 configuraciones son invocables por bandera |
| 10 | Test set 40–60, dataset card | prompts CONGELADOS |
| 11 | Experimentos | el test set se abre **una sola vez** |
| 12 | Análisis y empaquetado | Wilson, McNemar, bootstrap; repo HF |
| 13 | Informe IMRaD + sustentación | ~8.000 palabras |

**Punto de corte:** si el pipeline end-to-end no corre al final de la semana 8, el RAG se recorta a extensión declarada y la ablación corre con 4 configuraciones. El pipeline sí corre de punta a punta contra el kernel, así que por código no se activa, pero si la clave y el prover no llegan pronto la semana 9 se queda sin datos reales para decidir.

## Deuda declarada

- Las líneas base y la tasa de esqueletos no se han medido sobre dev, falta correrlas con Ollama y el prover servido. Es lo primero que hay que hacer cuando estén.
- El recall@k es bajo con consultas de puro símbolo, ver semanas 5–6.
- PutnamBench no se ingirió. Es el benchmark secundario y sus enunciados traen definiciones de solución (`abbrev ..._solution`) que hay que manejar aparte, se deja para la semana 10 cuando se arme el test set.
- `docs/references.bib` no existe. Las 27 entradas de `related-work.md` están escritas de memoria, hay que auditar venue, año y DOI contra la fuente antes de citarlas.
- Referencia del informe del MIT sin identificar (`related-work.md` eje 7).
