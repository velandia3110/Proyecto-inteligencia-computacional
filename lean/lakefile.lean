import Lake
open Lake DSL

package mathproj where
  -- Sin opciones de compilacion agresivas: el cache de Mathlib solo sirve si la
  -- configuracion coincide con la de upstream.

-- Pin por TAG de version, no por rama. El tag fija el commit; `mathlib-commit.txt`
-- lo resuelve a hash en el primer build y ese hash es el que se cita en el informe (RNF-2).
require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @ "v4.15.0"

@[default_target]
lean_lib MathProj where
