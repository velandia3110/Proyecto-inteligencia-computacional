---
title: mathagents
sdk: gradio
sdk_version: 4.44.1
app_file: app.py
license: apache-2.0
---

Reproduce trazas ya ejecutadas del sistema multiagente sobre miniF2F. Lean 4 + Mathlib no
corren aqui (varios GB, arranque lento; riesgo §8.3 del documento de diseño): la verificación
en vivo solo responde para pruebas cuyo texto coincide con una que el kernel ya juzgó en la
corrida. Cualquier otra prueba se verifica en local con la imagen Docker del repositorio.
