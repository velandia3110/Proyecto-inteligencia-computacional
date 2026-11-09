# Guion de la sustentación

Sistema multiagente de resolución matemática verificada por Lean 4 · Inteligencia Artificial, UPTC.
Duración objetivo: 15–18 minutos + preguntas. 14 diapositivas. Los `[[RESULT: ...]]` se rellenan
con la salida de `python -m src.analysis` después de la semana 11; no se presenta ningún número
que no salga de `runs/*.jsonl`. Sin emojis; los iconos, si se usan, salen de la librería de iconos
de la herramienta de diapositivas.

---

## 1. Título

**Plausible no es demostrado: un sistema multiagente con presupuesto, verificado por el kernel de Lean 4**

- [[AUTHORS: nombres]] · Inteligencia Artificial · UPTC · [[DATE]]

*Notas del orador.* Una frase de entrada: "Un modelo de lenguaje escribe demostraciones que se leen
bien y muchas veces son falsas. Construimos un sistema donde eso no importa, porque quien decide
no es el modelo sino el kernel de Lean".

## 2. El problema

- Los LLM generan derivaciones plausibles y falsas; su confianza no indica corrección.
- Los benchmarks informales (MATH) califican la respuesta final, no los pasos.
- Generar y verificar son regímenes asimétricos: generar es barato y falible, verificar es rígido.

*Notas.* Mostrar un ejemplo corto de paso falso con respuesta correcta si hay tiempo. La idea a
dejar clara: no peleamos contra el error del modelo, lo dejamos equivocarse y filtramos con el kernel.

## 3. Criterio único de éxito

- Resuelto si y solo si el kernel acepta la prueba ensamblada.
- Sin `sorry`, sin axiomas fuera de {`propext`, `Classical.choice`, `Quot.sound`}.
- El enunciado no puede cambiar (`STATEMENT_CHANGED` ni llega al kernel).

*Notas.* Explicar por qué existen `SORRY` y `AXIOM`: `axiom cheat : False` compila y prueba
cualquier cosa. Sin esos dos veredictos la métrica principal sería falsificable.

## 4. Arquitectura: seis agentes

- Planificador, Recuperador, Generador, Autoformalizador, Verificador, Crítico.
- Contratos JSON Schema en cada frontera (RNF-4); prompts versionados como archivos.
- Verificador determinista: no es un LLM.

*Notas.* Diagrama de tres capas: problema arriba, orquestador LangGraph en el medio, recursos
locales abajo (Ollama, prover, FAISS, REPL de Lean). Toda llamada pasa por una sola función que
cobra presupuesto y escribe una línea JSONL.

## 5. Grafo de estados

- PLAN → VERIFY_SKELETON → [RETRIEVE → GENERATE → FORMALIZE → VERIFY (→ CRITIQUE)]* → ASSEMBLE → VERIFY_FINAL.
- Dos estados que la propuesta original no tenía: VERIFY_SKELETON y ASSEMBLE/VERIFY_FINAL.
- Solo VERIFY_FINAL produce SOLVED.

*Notas.* Recorrer las aristas del Crítico: sintaxis → reformalizar; lema faltante → recuperar más
(k 10 → 20, tope 50); metas abiertas → nuevo boceto; error de planificación → replanificar (una vez).

## 6. La idea central: verificar el esqueleto

- El plan es Lean: un `have … := by sorry` por subobjetivo.
- Si compila con los `sorry`, los subobjetivos implican el teorema.
- Tres chequeos extra: enunciado igual, cada `have` presente, ningún `sorry` escondido.

*Notas.* Mostrar `mathd_algebra_478` con step1/step2 y `linarith`. Diferencia con Draft, Sketch and
Prove: allí el boceto no se verifica antes de intentar cerrarlo. Aquí la descomposición es
falsable, no esperanzada.

## 7. Recuperador y recall@k medido

- 179.269 premisas del mismo commit de Mathlib (252.002 antes de quitar autogenerados).
- BGE-M3 + FAISS `IndexFlatIP`: búsqueda exacta, coseno.
- recall@k sobre 1.000 teoremas: 0,173 (k=5) · 0,224 (k=10) · 0,287 (k=20) · 0,362 (k=50).

*Notas.* Decirlo tal cual: son bajos. Con nombre en la consulta el lema sale primero (0,85); con
puro símbolo (`0 ≤ x ^ 2`) `sq_nonneg` ni sale en el top 5. La verdad de referencia es ruidosa
(términos de prueba). Se usa k=10.

## 8. Decisiones que hacen la ablación honesta

- D2: el prover en modo estándar, sin autocorrección interna; todo reintento pasa por el Crítico.
- Sin Crítico, se reintenta a ciegas con el mismo tope (2 intentos por subobjetivo).
- El Crítico solo clasifica y diagnostica; la acción la pone el código con una tabla fija.

*Notas.* Si la autocorrección del prover quedara activa, "sin Crítico" seguiría teniendo un crítico
adentro. Consecuencia declarada: la línea base es más débil que el prover de fábrica.

## 9. Presupuesto D3 y modelos locales

- Techo duro de 20 llamadas por problema: es un `raise`, no un aviso (`BUDGET_EXHAUSTED`).
- n=2 bocetos solo en el primer intento; corte temprano si es irrecuperable.
- Qwen3-4B-Instruct en Ollama (costo 0 por token) + Goedel-Prover-V2-8B servido aparte.

*Notas.* Por qué local: no había presupuesto para la API. Lo que se pierde: calidad de planificación,
y los números no son comparables con sistemas de API. Lo que se mantiene: la ablación, porque las
cinco configuraciones usan los mismos modelos. La variante que razona gastó 8.192 tokens (~29 min)
sin responder: por eso instruct, sin thinking y JSON forzado.

## 10. Adelanto D4 y lo que solo apareció con Lean real

- Entorno Lean adelantado a la semana 1; compuerta `2 + 2 = 4` desde Python (se cerró en la semana 3).
- 244/244 enunciados de dev compilan; Verificador 13/13 fabricados y 8/8 contra el kernel.
- Seis errores invisibles con respuestas fabricadas: REPL sin `lake env`, Unicode escapado,
  Lean 3 como lema faltante, desbordamiento de pila, REPL huérfano, esqueleto vs JSON.

*Notas.* Lección: las respuestas fabricadas confirman lo que uno cree que hace el sistema, no lo que
hace. Mostrar `mathd_algebra_48` pasando todo el grafo con el kernel real decidiendo.

## 11. Protocolo experimental

- Cinco configuraciones: baseline_a, baseline_b, agents_only, no_critic, full.
- Ajuste solo en dev; prompts congelados en la semana 10; test de 50 problemas estratificado, abierto una vez.
- Wilson 95 %, McNemar exacto con Bonferroni (10 pares, α = 0,005), bootstrap pareado (10.000).

*Notas.* Declarar desde ya que con n=50 el estudio es exploratorio: se reportan tamaños de efecto
con intervalos, no se prometen significancias que el diseño no puede dar.

## 12. Resultados

- Tasa de resolución por configuración: [[RESULT: tabla de las 5 configuraciones con resueltos/50, tasa e IC de Wilson]].
- Efecto del RAG (agents_only → no_critic): [[RESULT: Δ e IC bootstrap, p de McNemar]].
- Efecto del Crítico (no_critic → full): [[RESULT: Δ e IC bootstrap, p de McNemar]].
- Llamadas por problema resuelto en full: [[RESULT: media y máximo frente al techo de 20]].
- Tasa de esqueletos válidos (test): [[RESULT: x/50 e IC]].

*Notas.* Leer primero los intervalos, después las diferencias. Si un IC cruza 0, decirlo así:
"no podemos distinguir el efecto del ruido con 50 problemas".

## 13. Falsos positivos evitados

- De las pruebas que el modelo declaró correctas, el kernel rechazó [[RESULT: x/y, tasa e IC de Wilson]].
- Desglose del rechazo: [[RESULT: FORMALIZATION_FAILED frente a veredictos del kernel]].
- Es una cota superior del error de autoevaluación (incluye fallos de traducción).

*Notas.* Este es el resultado que más se transfiere al uso diario: la confianza del modelo no es una
señal de corrección. Enlazar con el principio del informe del MIT (2026): la IA como herramienta
bajo dirección de una persona responsable de verificar la salida; aquí esa verificación la hace el
kernel.

## 14. Limitaciones y conclusión

- Línea base del prover debilitada a propósito (D2); modelos de 4B; recall bajo con consultas
  simbólicas; n=50 con una sola semilla; PutnamBench [[RESULT: estado final]].
- Aporte: esqueleto verificado antes de probar, presupuesto auditable, medición de falsos positivos.
- Trabajo futuro: consultas en lenguaje natural al recuperador, test más grande, planificador más fuerte.

*Notas.* Cerrar con la frase: "Plausible no es demostrado. El sistema deja que el modelo se
equivoque y no deja que se equivoque en el resultado". Pasar a preguntas.

---

## Preguntas probables y respuesta corta

- **¿Por qué no usar el prover con autocorrección y ya?** Porque la ablación dejaría de medir al
  Crítico (D2). Se reporta el número publicado como referencia externa, no comparable.
- **¿Por qué un modelo de 4B?** Costo 0 por token, sin presupuesto para API. La ablación sigue
  siendo válida porque todas las configuraciones comparten modelos.
- **¿El recall tan bajo no invalida el RAG?** Es una cota pesimista (verdad de referencia ruidosa);
  el efecto real se mide en la tasa de resolución: [[RESULT: Δ RAG]].
- **¿Por qué no hay significancia estadística?** n=50 y Bonferroni sobre 10 pares; se declaró
  exploratorio antes de abrir el test.
- **¿Cómo saben que no hicieron trampa con el test?** El runner no abre el test sin `--abrir-test`,
  la lista de 50 ids está fijada por hash y los prompts se congelaron en la semana 10.
