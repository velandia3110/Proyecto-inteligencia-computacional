-- Raiz de la libreria. Solo existe para que `lake build` tenga un target y para
-- forzar que el cache de Mathlib quede materializado en la imagen.
import Mathlib

-- Compuerta del dia 5 de la semana 1 (decisions.md D4).
theorem smoke_test : 2 + 2 = 4 := by norm_num
