"""TIMEOUT y el pool de REPLs contra el kernel real. Necesita la imagen Docker:

    docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 python3 tests/test_kernel_pool.py

Cubre lo que test_kernel.py no: los tres caminos a TIMEOUT (reloj, heartbeats de
Lean, proceso muerto) y que el REPL se recupera despues; y ReplPool con dos REPLs
reales en paralelo.
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data import HEADER
from src.lean_repl import ReadyRepl
from src.repl_pool import ReplPool
from src.verify import verify

TRIVIAL = "theorem triv : (2 : ℕ) + 2 = 4 := by norm_num"

# Reloj: sin limite de heartbeats, ring_nf sobre (a+..+e)^12 corre > 90 s.
WALL = ("set_option maxHeartbeats 0 in\n"
        "theorem w1 (a b c d e : ℝ) : (a+b+c+d+e)^12 = (e+d+c+b+a)^12 := by ring_nf")

# Heartbeats: con los 400000 del HEADER esto tarda minutos en este equipo (~12 s por
# cada 20000), asi que se baja el limite; el mensaje de Lean es el mismo.
HEARTBEATS = ("set_option maxHeartbeats 20000 in\n"
              "theorem hb (a b c d : ℝ) (h : a + b + c + d = 0) : (a+b+c+d)^8 = 0 := by\n"
              "  nlinarith [sq_nonneg (a+b), sq_nonneg (c+d), sq_nonneg (a-b),"
              " sq_nonneg (c-d), sq_nonneg (a+c), sq_nonneg (b+d)]")

# Proceso muerto: decide con maxRecDepth alto desborda la pila y el REPL sale sin
# responder. Antes del arreglo en lean_repl.py esto daba SYNTAX_ERROR con raw vacio.
CRASH = ("set_option maxRecDepth 100000 in\n"
         "theorem cr : Nat.Prime 10007 := by decide")

POOL = [
    "theorem p1 (a b c d : ℝ) : (a+b+c+d)^7 = (d+c+b+a)^7 := by ring",
    "theorem p2 (x : ℕ) (h : x < 300) : x * x ≠ 3 := by interval_cases x <;> omega",
]


def check(label: str, want: str, v) -> bool:
    ok = v.verdict == want
    print(f"  {'ok ' if ok else 'MAL'} {label:22} -> {v.verdict:15} {v.elapsed_ms} ms")
    if not ok:
        print(v.raw[:600])
    return ok


def timeouts() -> int:
    repl = ReadyRepl(HEADER)
    fails = 0
    try:
        fails += not check("TIMEOUT reloj (5 s)", "TIMEOUT", verify(WALL, repl, "w1", timeout_s=5))
        fails += not check("  REPL revive -> OK", "OK", verify(TRIVIAL, repl, "triv", timeout_s=60))
        v = verify(HEARTBEATS, repl, "hb", timeout_s=120)
        fails += not check("TIMEOUT heartbeats", "TIMEOUT", v)
        print(f"      mensaje: {v.raw.split('(deterministic)')[-1][:90]!r}")
        v = verify(CRASH, repl, "cr", timeout_s=120)
        fails += not check("TIMEOUT proceso muerto", "TIMEOUT", v)
        print(f"      raw: {v.raw!r}")
        fails += not check("  REPL revive -> OK", "OK", verify(TRIVIAL, repl, "triv", timeout_s=60))
    finally:
        repl.close()
    # Matar a `lake` sin su hijo dejaba el repl del timeout vivo, con GB de RAM.
    left = rss_repls()
    fails += left != 0
    print(f"  {'ok ' if not left else 'MAL'} sin repl huerfanos     -> {left} vivos")
    return fails


def rss_repls() -> int:
    """RSS de cada proceso `repl` vivo (incluye los .olean de Mathlib mapeados, RssFile).
    Devuelve cuantos hay."""
    n = 0
    for status in Path("/proc").glob("[0-9]*/status"):
        try:
            txt = status.read_text()
        except OSError:
            continue
        f = dict(line.split(":", 1) for line in txt.splitlines() if ":" in line)
        if f.get("Name", "").strip() == "repl" and "VmRSS" in f:  # sin VmRSS = zombi
            n += 1
            print(f"      repl pid {f['Pid'].strip()}: VmRSS {f['VmRSS'].strip()}"
                  f" (anon {f.get('RssAnon', '?').strip()}, file {f.get('RssFile', '?').strip()})")
    return n


def pool() -> int:
    t = time.monotonic()
    p = ReplPool(HEADER, size=2)
    print(f"      pool de 2 levantado en {time.monotonic() - t:.0f} s")
    rss_repls()
    fails = 0
    try:
        # serie: cada teorema solo, para tener con que comparar
        serial = 0.0
        for code in POOL:
            with p.acquire() as r:
                t = time.monotonic()
                verify(code, r, code.split()[1], timeout_s=120)
                serial += time.monotonic() - t

        verdicts: dict[int, str] = {}

        def work(i: int) -> None:
            with p.acquire() as r:
                verdicts[i] = verify(POOL[i], r, POOL[i].split()[1], timeout_s=120).verdict

        t = time.monotonic()
        ths = [threading.Thread(target=work, args=(i,)) for i in range(len(POOL))]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        par = time.monotonic() - t
        for i in range(len(POOL)):
            ok = verdicts.get(i) == "OK"
            fails += not ok
            print(f"  {'ok ' if ok else 'MAL'} pool hilo {i}            -> {verdicts.get(i)}")
        print(f"      serie {serial:.1f} s, paralelo {par:.1f} s")
        rss_repls()
    finally:
        p.close()
    return fails


def main() -> int:
    fails = timeouts() + pool()
    total = 6 + len(POOL)
    print(f"\n{total - fails}/{total} pasan")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
