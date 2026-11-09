# Marco teórico y revisión de literatura

Objetivo específico 1. Organizada **por eje temático**, no cronológicamente. La columna
*Qué aporta a nuestro diseño* es la que convierte esta tabla en la sección *Related Work* del
informe: cada fila debe justificar una decisión concreta, no describir el paper.

28 referencias primarias en los ejes 1–6 más el informe institucional del eje 7 (mínimo exigido: 15).
Auditadas contra la fuente el 2026-11-09 y volcadas a `docs/references.bib` (clave BibTeX al final
de cada fila). Ver *Auditoría bibliográfica* al final.

> **Auditoría hecha (2026-11-09).** Cada entrada se contrastó con arXiv (API oficial), Crossref (DOI,
> volumen, páginas) y la página del venue (NeurIPS, ICLR, ACL Anthology, Nature, ACM). Las correcciones
> están en la tabla del final. No se cita nada que no se haya abierto.

---

## Eje 1 — Transformers y modelos de lenguaje

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 1 | Vaswani et al. (2017). *Attention Is All You Need*. NeurIPS (entonces NIPS). arXiv:1706.03762. `[vaswani2017attention]` | Base arquitectónica de todo lo demás. Justifica en el informe por qué el costo por llamada escala con la longitud del contexto, que es lo que limita cuántos lemas recuperados caben en el prompt del Autoformalizador. |
| 2 | Brown et al. (2020). *Language Models are Few-Shot Learners*. NeurIPS. arXiv:2005.14165. `[brown2020language]` | In-context learning: funda la estrategia de prompting con ejemplos en lugar de fine-tuning. Nosotros no entrenamos nada. |
| 3 | Ouyang et al. (2022). *Training language models to follow instructions with human feedback*. NeurIPS. arXiv:2203.02155. `[ouyang2022training]` | Explica por qué un modelo instruido obedece un contrato JSON. Es el supuesto sobre el que descansa el RNF-4. |

## Eje 2 — Cadenas de razonamiento

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 4 | Wei et al. (2022). *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models*. NeurIPS. arXiv:2201.11903. `[wei2022chain]` | Mecanismo del Generador y de la línea base B. También la advertencia central: CoT mejora la plausibilidad, no la corrección. Es la premisa del proyecto. |
| 5 | Wang et al. (2023). *Self-Consistency Improves Chain of Thought Reasoning in Language Models*. ICLR. arXiv:2203.11171. `[wang2023selfconsistency]` | Justifica el muestreo n=2 del Generador con voto por acuerdo estructural. Su costo es lo que obliga a n=1 en reintentos (RNF-3). |
| 6 | Yao et al. (2023). *Tree of Thoughts: Deliberate Problem Solving with Large Language Models*. NeurIPS. arXiv:2305.10601. `[yao2023tree]` | Alternativa de búsqueda al CoT lineal. **Decisión: fuera del alcance** salvo que sobre tiempo; CoT con replanificación ya cubre el eje del curso y ToT multiplica las llamadas. |
| 7 | Hendrycks et al. (2021). *Measuring Mathematical Problem Solving With the MATH Dataset*. NeurIPS D&B. arXiv:2103.03874. `[hendrycks2021math]` | Referencia de rendimiento en matemáticas **no** verificadas. Contraste cuantitativo para argumentar que la evaluación por coincidencia de respuesta final no detecta derivaciones falsas. |

## Eje 3 — IA agéntica y sistemas multiagente

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 8 | Yao et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR. arXiv:2210.03629. `[yao2023react]` | Patrón razonar-actuar-observar. Nuestro ciclo FORMALIZE → VERIFY → CRITIQUE es ReAct donde la observación la produce el kernel, no una API difusa. |
| 9 | Shinn et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS. arXiv:2303.11366. `[shinn2023reflexion]` | Antecedente directo del Crítico: realimentación verbal del error en el prompt del reintento (RF-6). Diferencia clave: en Reflexion la autocrítica la emite el propio modelo; aquí la emite el compilador. |
| 10 | Wu et al. (2024). *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*. COLM 2024. arXiv:2308.08155. `[wu2024autogen]` | Referente de orquestación conversacional. Se descarta a favor de LangGraph por estado tipado y checkpoints (`decisions.md` D1.1). Justifica la comparación de frameworks en el informe. |
| 11 | Park et al. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. UIST. doi:10.1145/3586183.3606763. `[park2023generative]` | Arquitectura de agentes con memoria y reflexión. Aporta el vocabulario de diseño; su memoria episódica es análoga a nuestro historial `attempts`. |

## Eje 4 — Embeddings y RAG

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 12 | Lewis et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS. arXiv:2005.11401. `[lewis2020rag]` | Formulación canónica del RAG. Nuestra base de conocimiento es Mathlib en lugar de Wikipedia; el argumento de que el conocimiento externo reduce la alucinación se traslada al caso de nombres de lemas (veredicto `MISSING_LEMMA`). |
| 13 | Karpukhin et al. (2020). *Dense Passage Retrieval for Open-Domain Question Answering*. EMNLP. doi:10.18653/v1/2020.emnlp-main.550. `[karpukhin2020dpr]` | Recuperación densa por producto interno; funda la §4 del documento de diseño y la métrica recall@k. |
| 14 | Chen et al. (2024). *M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation* (BGE-M3). Findings of ACL 2024. doi:10.18653/v1/2024.findings-acl.137. `[chen2024m3]` | Modelo de embeddings elegido (D1.6). Multilingüe y de contexto largo, que importa porque un tipo de Lean pretty-printed es largo y no es prosa. |
| 15 | Wang et al. (2022). *Text Embeddings by Weakly-Supervised Contrastive Pre-training* (E5). Preprint arXiv:2212.03533. `[wang2022e5]` | Alternativa evaluada a BGE-M3. Se registra la comparación para justificar la elección, no para usarla. |
| 16 | Johnson, Douze & Jégou (2021). *Billion-scale similarity search with GPUs*. IEEE Trans. Big Data 7(3):535–547. doi:10.1109/TBDATA.2019.2921572. `[johnson2021faiss]` | FAISS. Justifica `IndexFlatIP` (exhaustivo, exacto) frente a un índice aproximado: con ~2·10⁵ premisas no hace falta aproximar, y así ningún fallo de recall es atribuible al índice. |

## Eje 5 — Verificación formal y asistentes de prueba

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 17 | de Moura & Ullrich (2021). *The Lean 4 Theorem Prover and Programming Language*. CADE-28, LNCS 12699:625–635. doi:10.1007/978-3-030-79876-5_37. `[demoura2021lean4]` | El kernel que decide. Su arquitectura de kernel pequeño es lo que hace defendible la afirmación "verificado". |
| 18 | The mathlib Community (2020). *The Lean Mathematical Library*. CPP, 367–381. doi:10.1145/3372885.3373824. `[mathlib2020]` | El corpus del RAG. Su tamaño y convenciones de nombres explican por qué recuperar premisas es necesario y por qué el modelo alucina identificadores. |
| 19 | Polu & Sutskever (2020). *Generative Language Modeling for Automated Theorem Proving*. Preprint arXiv:2009.03393. `[polu2020generative]` | Primer LLM generador de pruebas formales. Origen de la métrica pass@k que usamos en la §12. |
| 20 | Wu et al. (2022). *Autoformalization with Large Language Models*. NeurIPS. arXiv:2205.12615. `[wu2022autoformalization]` | Define la tarea del Autoformalizador y documenta su tasa de fallo. Sustenta separar `FORMALIZATION_FAILED` de `VERIFY_FAILED` (RF-4): son fallos de traducción, no de matemática. |
| 21 | Jiang et al. (2023). *Draft, Sketch, and Prove: Guiding Formal Theorem Provers with Informal Proofs*. ICLR. arXiv:2210.12283. `[jiang2023dsp]` | **La referencia más cercana a nuestra arquitectura.** Boceto informal → esqueleto formal → cierre de huecos. Nuestro aporte sobre ella: verificar el esqueleto (`VERIFY_SKELETON`) y orquestar con agentes explícitos y presupuesto. |
| 22 | Yang et al. (2023). *LeanDojo: Theorem Proving with Retrieval-Augmented Language Models*. NeurIPS D&B. arXiv:2306.15626. `[yang2023leandojo]` | Doble uso: corpus de premisas ya extraído (no parseamos Mathlib) **y** anotación de qué premisas usa realmente cada prueba, que es el ground truth de la evaluación aislada del retriever en la semana 6. |
| 23 | First et al. (2023). *Baldur: Whole-Proof Generation and Repair with Large Language Models*. ESEC/FSE, 1229–1241. doi:10.1145/3611643.3616243. `[first2023baldur]` | Reparación de prueba condicionada al mensaje de error. Evidencia directa a favor del RF-6 (inyectar el error de Lean textualmente en el reintento). |
| 24 | Xin et al. (2025). *DeepSeek-Prover-V1.5: Harnessing Proof Assistant Feedback for Reinforcement Learning and Monte-Carlo Tree Search*. ICLR 2025. arXiv:2408.08152. `[xin2025deepseekprover]` | Realimentación del asistente de pruebas + búsqueda. Línea base de referencia del estado del arte y origen del riesgo de solapamiento con nuestro Crítico (D2). |
| 25 | Lin et al. (2026). *Goedel-Prover-V2: Scaling Formal Theorem Proving with Scaffolded Data Synthesis and Self-Correction*. ICLR 2026. arXiv:2508.03613. `[lin2026goedel]` | Modelo de formalización elegido (D1.5). El modo de invocación sin autocorrección interna (*standard mode*) quedó verificado en el README oficial del modelo (`decisions.md`, historial 2026-09-27); de ahí depende que la ablación mida algo. |

## Eje 6 — Problemas complejos y benchmarks

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 26 | Zheng, Han & Polu (2022). *miniF2F: a cross-system benchmark for formal Olympiad-level mathematics*. ICLR. arXiv:2109.00110. `[zheng2022minif2f]` | Benchmark primario. Enunciados ya formalizados y auditados: elimina el riesgo de mal-formalizar el enunciado (§11). |
| 27 | Tsoukalas et al. (2024). *PutnamBench: Evaluating Neural Theorem-Provers on the Putnam Mathematical Competition*. NeurIPS D&B. arXiv:2407.11214. `[tsoukalas2024putnambench]` | Benchmark secundario, banda superior de dificultad. Fuente de problemas si miniF2F resulta demasiado fácil en el pilotaje de la semana 4. |
| 28 | Trinh et al. (2024). *Solving olympiad geometry without human demonstrations*. Nature 625:476–482. doi:10.1038/s41586-023-06747-5. `[trinh2024alphageometry]` | AlphaGeometry: prueba de que el acople neuro-simbólico funciona a nivel olimpiada. Es el argumento de cierre del marco teórico. |

## Eje 7 — Consideraciones éticas

| # | Referencia | Qué aporta a nuestro diseño |
|---|---|---|
| 29 | MIT Ad Hoc Committee on AI Use (2026). *Report of MIT's Ad Hoc Committee on AI Use in Teaching, Learning, and Research Training*. Massachusetts Institute of Technology, 13 de agosto de 2026. Informe institucional, no revisado por pares. `[mit2026aicommittee]` | Encuadre *augmentation not automation*, principio de IA como herramienta bajo dirección humana responsable de verificar la salida (que es literalmente el RNF-1), y modelo para la declaración de uso de IA (su apéndice A). Sección *Ethical Considerations*. |

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

---

## Auditoría bibliográfica (2026-11-09)

Fuentes: API de arXiv (los 27 identificadores resuelven y coinciden en título y autores), Crossref
(DOI, volumen, páginas), páginas oficiales de NeurIPS/ICLR/COLM, ACL Anthology, Nature y ACM.
Todas las entradas quedaron verificadas; ninguna se marcó como no verificable.

| # | Campo | Antes (de memoria) | Después (verificado) | Fuente |
|---|---|---|---|---|
| 4 | título | *…Elicits Reasoning in LLMs* | *…Elicits Reasoning in Large Language Models* | arXiv:2201.11903 |
| 5 | título | *Self-Consistency Improves Chain of Thought Reasoning* | *…Reasoning in Language Models* | arXiv:2203.11171 (camera-ready ICLR 2023) |
| 6 | título | *…Problem Solving with LLMs* | *…Problem Solving with Large Language Models* | arXiv:2305.10601 (NeurIPS 2023) |
| 10 | año, venue | 2023, sin venue | 2024, COLM 2024 (versión previa en el workshop LLM Agents de ICLR 2024) | Microsoft Research, arXiv:2308.08155 |
| 13 | título | *…for Open-Domain QA* | *…for Open-Domain Question Answering*; DOI agregado | Crossref, ACL Anthology |
| 14 | título, venue | *BGE M3-Embedding*, sin venue | *M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation*, Findings of ACL 2024 | Crossref doi:10.18653/v1/2024.findings-acl.137 |
| 15 | venue | sin venue | preprint de arXiv (no se encontró versión revisada por pares) | arXiv:2212.03533, Microsoft Research |
| 16 | año | 2019 | 2021 (vol. 7, n.º 3, pp. 535–547; 2019 es la publicación anticipada en línea) | Crossref doi:10.1109/TBDATA.2019.2921572 |
| 19 | venue | sin venue | preprint de arXiv | arXiv:2009.03393 |
| 23 | título, venue | *…Repair with LLMs*, FSE | *…Repair with Large Language Models*, ESEC/FSE 2023 | Crossref doi:10.1145/3611643.3616243 |
| 24 | año, título, venue | 2024, título corto, sin venue | 2025, título completo, ICLR 2025 | iclr.cc/virtual/2025/poster/30193 |
| 25 | año, título, venue | 2025, título corto, sin venue | 2026, título completo, ICLR 2026 | proceedings.iclr.cc (2026), arXiv:2508.03613 |
| 25 | nota | "Verificar en el paper" el modo sin autocorrección | ya verificado en el README del modelo (`decisions.md`, 2026-09-27) | — |
| 27 | título | *PutnamBench* | *PutnamBench: Evaluating Neural Theorem-Provers on the Putnam Mathematical Competition* | arXiv:2407.11214 |
| 29 | cita completa | **PENDIENTE** "informe del MIT sobre IA y trabajo" | *Report of MIT's Ad Hoc Committee on AI Use in Teaching, Learning, and Research Training*, MIT, 13 de agosto de 2026 | PDF del informe (ver abajo) |
| — | conteo | "27 referencias primarias" | 28 en los ejes 1–6 + 1 informe institucional (eje 7) = 29 filas | la tabla ya tenía 29 filas |

Sin cambios de fondo (solo se agregó arXiv id o DOI): 1, 2, 3, 7, 8, 9, 11, 12, 17, 18, 20, 21,
22, 26, 28. Notas menores: [1] apareció cuando la conferencia aún se llamaba NIPS; [9] la página de
NeurIPS lista 5 autores y arXiv v4 agrega a Edward Berman (en el `.bib` se usa la de arXiv).

**Sobre la referencia 29.** Coincide en los tres puntos que la fila le atribuye: la sección 2.7 se
titula *"Augmentation not automation"*; la sección 3.2 dice que todo investigador debe "view AI as
a tool under the direction of a human who is responsible for verifying the accuracy of its output";
y el Apéndice A (*Committee Process*) cierra con una declaración *"AI Use"* sobre cómo el comité usó
ChatGPT y Codex. No es un informe sobre "IA y trabajo" sino sobre uso de IA en docencia e
investigación; se descartó *Humans in the Loop* (MIT IPC, abril de 2026), que sí trata IA y trabajo
pero no tiene apéndice de declaración de uso. Es un informe institucional, no revisado por pares.
URL: <https://bpb-us-e1.wpmucdn.com/sites.mit.edu/dist/d/2418/files/2026/09/AI-Committee-Final-Report-Aug-13.pdf>

**Entradas nuevas en `references.bib`** que no están en esta tabla porque son de metodología, no
de marco teórico: Qwen3 (arXiv:2505.09388), Ollama, LangGraph, el REPL de Lean, vLLM (SOSP 2023),
Wilson (1927), McNemar (1947), Dunn/Bonferroni (1961) y Efron (1979), todas verificadas en Crossref
o arXiv salvo el software, que se cita por URL.
