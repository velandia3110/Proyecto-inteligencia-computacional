"""Pool de REPLs de Lean (semana 7).

Levantar un REPL con Mathlib cuesta segundos y varios cientos de MB, entonces se
levantan N una vez y cada problema toma uno prestado mientras dura. Un REPL que
murio por timeout se relevanta solo la proxima vez que se usa (ReadyRepl).

N = numero de problemas en paralelo. Medido (tests/test_kernel_pool.py): cada REPL
marca ~4 GB residentes, pero ~3.9 GB son los archivos de Mathlib mapeados y se
comparten entre todos; lo propio de cada uno es ~0.3-0.4 GB en reposo y puede
subir a ~3 GB con una tactica pesada. Con los 8 GB de Docker Desktop: 2-3.
"""

from __future__ import annotations

import queue
from contextlib import contextmanager

from src.lean_repl import ReadyRepl


class ReplPool:
    def __init__(self, header: str, size: int = 2, factory=ReadyRepl):
        self._all = [factory(header) for _ in range(size)]
        self._free: queue.Queue = queue.Queue()
        for r in self._all:
            self._free.put(r)

    @contextmanager
    def acquire(self):
        repl = self._free.get()
        try:
            yield repl
        finally:
            self._free.put(repl)

    def close(self) -> None:
        for r in self._all:
            r.close()
