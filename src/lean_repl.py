"""Cliente del REPL de Lean (leanprover-community/repl).

Protocolo: se envia un objeto JSON en una linea, seguido de una linea en blanco.
El REPL responde con un objeto JSON seguido de una linea en blanco.

El proceso se mantiene vivo entre llamadas: levantar un REPL nuevo por verificacion
cuesta ~30 s de carga de Mathlib. El pool de procesos de la semana 7 se construye
encima de esta clase.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field


@dataclass
class ReplResult:
    """Respuesta cruda del REPL, ya normalizada."""

    raw: str
    messages: list[dict] = field(default_factory=list)
    sorries: list[dict] = field(default_factory=list)
    env: int | None = None
    timed_out: bool = False

    @property
    def errors(self) -> list[str]:
        return [m.get("data", "") for m in self.messages if m.get("severity") == "error"]

    @property
    def infos(self) -> list[str]:
        return [m.get("data", "") for m in self.messages if m.get("severity") == "info"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_sorries(self) -> bool:
        # El REPL reporta los sorries en su propio campo, pero algunas versiones
        # solo emiten el warning. Se cubren los dos.
        return bool(self.sorries) or any(
            "declaration uses 'sorry'" in m.get("data", "") for m in self.messages
        )


class LeanRepl:
    """Un proceso REPL de larga vida. No es thread-safe por si mismo: usa el lock."""

    def __init__(self, repl_bin: str | None = None, project_dir: str | None = None):
        self.repl_bin = repl_bin or os.environ.get(
            "LEAN_REPL_BIN", "/app/repl/.lake/build/bin/repl"
        )
        self.project_dir = project_dir or os.environ.get("LEAN_PROJECT_DIR", "/app/mathproj")
        self._lock = threading.Lock()
        # `lake env` pone el LEAN_PATH del proyecto. Sin el, el REPL no encuentra ni el
        # prelude y el `import Mathlib` "funciona" en silencio sin cargar nada.
        self._proc = subprocess.Popen(
            ["lake", "env", self.repl_bin],
            cwd=self.project_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def run(self, cmd: str, env: int | None = None, timeout: float = 120.0) -> ReplResult:
        payload: dict = {"cmd": cmd}
        if env is not None:
            payload["env"] = env

        with self._lock:
            try:
                # ensure_ascii=False: el REPL no decodifica los pares sustitutos (\ud835...)
                # y un `𝓝` escapado da "expected token". Visto en mathd_algebra_31.
                out = self._exchange(json.dumps(payload, ensure_ascii=False), timeout)
            except subprocess.TimeoutExpired:
                # El REPL queda en estado indefinido tras un timeout: se recicla.
                self.close()
                return ReplResult(raw="<timeout>", timed_out=True)

        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return ReplResult(raw=out, messages=[{"severity": "error", "data": out}])

        return ReplResult(
            raw=out,
            messages=data.get("messages", []),
            sorries=data.get("sorries", []),
            env=data.get("env"),
        )

    def _exchange(self, line: str, timeout: float) -> str:
        """Escribe una peticion y lee hasta la linea en blanco que cierra la respuesta."""
        assert self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(line + "\n\n")
        self._proc.stdin.flush()

        chunks: list[str] = []
        result: list[str] = []

        def reader() -> None:
            for out_line in self._proc.stdout:  # type: ignore[union-attr]
                if out_line.strip() == "" and chunks:
                    break
                chunks.append(out_line)
            result.append("".join(chunks))

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise subprocess.TimeoutExpired(self.repl_bin, timeout)
        return result[0] if result else ""

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=5)

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def __enter__(self) -> "LeanRepl":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class ReadyRepl:
    """REPL con el encabezado comun (import Mathlib + opens) ya cargado.

    Cada `run` sin `env` corre sobre el entorno del encabezado, asi los problemas no
    se ven entre si. Si un timeout mato el proceso, se levanta otro en la siguiente
    llamada (cuesta la recarga de Mathlib, pero no tumba la corrida).
    """

    def __init__(self, header: str, **kw):
        self.header = header
        self.kw = kw
        self._spawn()

    def _spawn(self) -> None:
        self.repl = LeanRepl(**self.kw)
        r = self.repl.run(self.header, timeout=600)
        if r.has_errors or r.env is None:
            raise RuntimeError(f"el encabezado no carga: {r.raw[:500]}")
        self.base_env = r.env

    def run(self, cmd: str, env: int | None = None, timeout: float = 120.0) -> ReplResult:
        if not self.repl.alive:
            self._spawn()
        return self.repl.run(cmd, env=self.base_env if env is None else env, timeout=timeout)

    def close(self) -> None:
        self.repl.close()
