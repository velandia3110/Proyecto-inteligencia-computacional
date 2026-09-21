"""Presupuesto de llamadas LLM (RNF-3: <=20 por problema resuelto).

No es un aviso, es un techo duro: al excederlo levanta BudgetExhausted y el grafo
registra el veredicto BUDGET_EXHAUSTED. Sin el `raise`, el RNF-3 es una aspiracion.

Ver decisions.md seccion D3 para la derivacion del techo.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class Budget:
    max_llm_calls: int = 20
    used: int = 0
    by_agent: Counter[str] = field(default_factory=Counter)

    def spend(self, agent: str, n: int = 1) -> None:
        if self.used + n > self.max_llm_calls:
            raise BudgetExhausted(
                f"{self.used}+{n} > {self.max_llm_calls} llamadas "
                f"(por agente: {dict(self.by_agent)})"
            )
        self.used += n
        self.by_agent[agent] += n

    @property
    def remaining(self) -> int:
        return self.max_llm_calls - self.used

    def can_afford(self, n: int) -> bool:
        """Para el corte temprano: no arrancar un reintento que no cabe."""
        return self.remaining >= n
