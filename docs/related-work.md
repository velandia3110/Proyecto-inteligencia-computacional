# Marco teórico y revisión de literatura

Objetivo específico 1. Organizada **por eje temático**, no cronológicamente. La columna
*Qué aporta a nuestro diseño* es la que convierte esta tabla en la sección *Related Work* del
informe: cada fila debe justificar una decisión concreta, no describir el paper.

27 referencias primarias (mínimo exigido: 15).

> **Pendiente antes de entregar:** verificar DOI/venue de cada entrada contra la fuente original
> y volcarlas a `docs/references.bib`. Las columnas de venue y año están escritas de memoria y
> deben auditarse una por una. No citar nada que no se haya abierto.

---

## Eje 1 — Transformers y modelos de lenguaje

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 1 | Vaswani et al. (2017). *Attention Is All You Need*. NeurIPS. | Base arquitectónica de todo lo demás. Justifica en el informe por qué el costo por llamada escala con la longitud del contexto, que es lo que limita cuántos lemas recuperados caben en el prompt del Autoformalizador. |
| 2 | Brown et al. (2020). *Language Models are Few-Shot Learners*. NeurIPS. | In-context learning: funda la estrategia de prompting con ejemplos en lugar de fine-tuning. Nosotros no entrenamos nada. |
| 3 | Ouyang et al. (2022). *Training language models to follow instructions with human feedback*. NeurIPS. | Explica por qué un modelo instruido obedece un contrato JSON. Es el supuesto sobre el que descansa el RNF-4. |

## Eje 2 — Cadenas de razonamiento

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 4 | Wei et al. (2022). *Chain-of-Thought Prompting Elicits Reasoning in LLMs*. NeurIPS. | Mecanismo del Generador y de la línea base B. También la advertencia central: CoT mejora la plausibilidad, no la corrección. Es la premisa del proyecto. |
| 5 | Wang et al. (2023). *Self-Consistency Improves Chain of Thought Reasoning*. ICLR. | Justifica el muestreo n=2 del Generador con voto por acuerdo estructural. Su costo es lo que obliga a n=1 en reintentos (RNF-3). |
| 6 | Yao et al. (2023). *Tree of Thoughts: Deliberate Problem Solving with LLMs*. NeurIPS. | Alternativa de búsqueda al CoT lineal. **Decisión: fuera del alcance** salvo que sobre tiempo; CoT con replanificación ya cubre el eje del curso y ToT multiplica las llamadas. |
| 7 | Hendrycks et al. (2021). *Measuring Mathematical Problem Solving With the MATH Dataset*. NeurIPS D&B. | Referencia de rendimiento en matemáticas **no** verificadas. Contraste cuantitativo para argumentar que la evaluación por coincidencia de respuesta final no detecta derivaciones falsas. |

## Eje 3 — IA agéntica y sistemas multiagente

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 8 | Yao et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR. | Patrón razonar-actuar-observar. Nuestro ciclo FORMALIZE → VERIFY → CRITIQUE es ReAct donde la observación la produce el kernel, no una API difusa. |
| 9 | Shinn et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS. | Antecedente directo del Crítico: realimentación verbal del error en el prompt del reintento (RF-6). Diferencia clave: en Reflexion la autocrítica la emite el propio modelo; aquí la emite el compilador. |
| 10 | Wu et al. (2023). *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*. | Referente de orquestación conversacional. Se descarta a favor de LangGraph por estado tipado y checkpoints (`decisions.md` D1.1). Justifica la comparación de frameworks en el informe. |
| 11 | Park et al. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. UIST. | Arquitectura de agentes con memoria y reflexión. Aporta el vocabulario de diseño; su memoria episódica es análoga a nuestro historial `attempts`. |

## Eje 4 — Embeddings y RAG

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 12 | Lewis et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS. | Formulación canónica del RAG. Nuestra base de conocimiento es Mathlib en lugar de Wikipedia; el argumento de que el conocimiento externo reduce la alucinación se traslada al caso de nombres de lemas (veredicto `MISSING_LEMMA`). |
| 13 | Karpukhin et al. (2020). *Dense Passage Retrieval for Open-Domain QA*. EMNLP. | Recuperación densa por producto interno; funda la §4 del documento de diseño y la métrica recall@k. |
| 14 | Chen et al. (2024). *BGE M3-Embedding*. | Modelo de embeddings elegido (D1.6). Multilingüe y de contexto largo, que importa porque un tipo de Lean pretty-printed es largo y no es prosa. |
| 15 | Wang et al. (2022). *Text Embeddings by Weakly-Supervised Contrastive Pre-training* (E5). | Alternativa evaluada a BGE-M3. Se registra la comparación para justificar la elección, no para usarla. |
| 16 | Johnson, Douze & Jégou (2019). *Billion-scale similarity search with GPUs*. IEEE Trans. Big Data. | FAISS. Justifica `IndexFlatIP` (exhaustivo, exacto) frente a un índice aproximado: con ~2·10⁵ premisas no hace falta aproximar, y así ningún fallo de recall es atribuible al índice. |

## Eje 5 — Verificación formal y asistentes de prueba

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 17 | de Moura & Ullrich (2021). *The Lean 4 Theorem Prover and Programming Language*. CADE. | El kernel que decide. Su arquitectura de kernel pequeño es lo que hace defendible la afirmación "verificado". |
| 18 | The mathlib Community (2020). *The Lean Mathematical Library*. CPP. | El corpus del RAG. Su tamaño y convenciones de nombres explican por qué recuperar premisas es necesario y por qué el modelo alucina identificadores. |
| 19 | Polu & Sutskever (2020). *Generative Language Modeling for Automated Theorem Proving*. | Primer LLM generador de pruebas formales. Origen de la métrica pass@k que usamos en la §12. |
| 20 | Wu et al. (2022). *Autoformalization with Large Language Models*. NeurIPS. | Define la tarea del Autoformalizador y documenta su tasa de fallo. Sustenta separar `FORMALIZATION_FAILED` de `VERIFY_FAILED` (RF-4): son fallos de traducción, no de matemática. |
| 21 | Jiang et al. (2023). *Draft, Sketch, and Prove*. ICLR. | **La referencia más cercana a nuestra arquitectura.** Boceto informal → esqueleto formal → cierre de huecos. Nuestro aporte sobre ella: verificar el esqueleto (`VERIFY_SKELETON`) y orquestar con agentes explícitos y presupuesto. |
| 22 | Yang et al. (2023). *LeanDojo: Theorem Proving with Retrieval-Augmented LMs*. NeurIPS D&B. | Doble uso: corpus de premisas ya extraído (no parseamos Mathlib) **y** anotación de qué premisas usa realmente cada prueba, que es el ground truth de la evaluación aislada del retriever en la semana 6. |
| 23 | First et al. (2023). *Baldur: Whole-Proof Generation and Repair with LLMs*. FSE. | Reparación de prueba condicionada al mensaje de error. Evidencia directa a favor del RF-6 (inyectar el error de Lean textualmente en el reintento). |
| 24 | Xin et al. (2024). *DeepSeek-Prover-V1.5*. | Realimentación del asistente de pruebas + búsqueda. Línea base de referencia del estado del arte y origen del riesgo de solapamiento con nuestro Crítico (D2). |
| 25 | Lin et al. (2025). *Goedel-Prover-V2*. | Modelo de formalización elegido (D1.5). **Verificar en el paper** el modo de invocación sin autocorrección interna; de ahí depende que la ablación mida algo. |

## Eje 6 — Problemas complejos y benchmarks

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 26 | Zheng, Han & Polu (2022). *miniF2F: a cross-system benchmark for formal Olympiad-level mathematics*. ICLR. | Benchmark primario. Enunciados ya formalizados y auditados: elimina el riesgo de mal-formalizar el enunciado (§11). |
| 27 | Tsoukalas et al. (2024). *PutnamBench*. NeurIPS D&B. | Benchmark secundario, banda superior de dificultad. Fuente de problemas si miniF2F resulta demasiado fácil en el pilotaje de la semana 4. |
| 28 | Trinh et al. (2024). *Solving olympiad geometry without human demonstrations*. Nature. | AlphaGeometry: prueba de que el acople neuro-simbólico funciona a nivel olimpiada. Es el argumento de cierre del marco teórico. |

## Eje 7 — Consideraciones éticas

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 29 | **PENDIENTE** — informe del MIT sobre IA y trabajo *(completar cita exacta)*. | Encuadre *augmentation not automation*, principio de IA como herramienta bajo dirección humana responsable de verificar la salida (que es literalmente el RNF-1), y modelo para la declaración de uso de IA (su apéndice A). Sección *Ethical Considerations*. |

---

## Cómo se usa esta tabla en el informe

*Related Work* (~1.200 palabras) se escribe recorriendo los ejes 2–6 en ese orden, y cada
párrafo cierra apuntando a la decisión de diseño que la referencia justifica. El eje 1 va
comprimido en dos frases: es contexto, no argumento.

**Posicionamiento frente al trabajo previo.** Draft-Sketch-Prove [21] ya encadena boceto informal
→ esqueleto → cierre. LeanDojo [22] ya recupera premisas. Baldur [23] ya repara con el mensaje de
error. Lo que no aparece junto en ninguno de los tres, y es lo que aportamos:

1. **verificar el esqueleto antes de probar nada** (`VERIFY_SKELETON`), que vuelve la
   descomposición falsable en lugar de esperanzada;
2. un **presupuesto de llamadas explícito y auditable** como restricción de diseño (RNF-3);
3. la medición de **falsos positivos evitados** contra la autoevaluación del propio modelo.

Ninguna de las tres pretende superar el estado del arte en pass@k. El proyecto no se evalúa por
rendimiento bruto.
