#!/usr/bin/env python3
"""
cost_estimator.py — Stima dei costi per il sistema ProjectMultiAgentAI

Versione: 1.0.0
Ultimo aggiornamento: 2026-02-22
Owner: platform-team

Questo modulo fornisce funzioni per stimare il costo delle operazioni AI
basandosi sul numero di token consumati e sul modello utilizzato.
"""


# Prezzi per 1M token (EUR, approssimati da USD con cambio ~0.92)
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 13.80, "output": 69.00},
    "claude-sonnet-4-6": {"input": 2.76, "output": 13.80},
    "claude-haiku-4-5": {"input": 0.74, "output": 3.68},
}


def estimate_cost(tokens_in: int, tokens_out: int, model: str = "claude-sonnet-4-6") -> float:
    """Stima il costo in EUR per una chiamata AI.

    Formula:
        cost = (tokens_in / 1_000_000 * price_input) + (tokens_out / 1_000_000 * price_output)

    Args:
        tokens_in:  Numero di token in input.
        tokens_out: Numero di token in output.
        model:      Identificativo del modello. Default: claude-sonnet-4-6.

    Returns:
        Costo stimato in EUR (float, arrotondato a 6 decimali).

    Raises:
        ValueError: Se il modello non è nella tabella prezzi.

    Example:
        >>> estimate_cost(1000, 500, "claude-sonnet-4-6")
        0.009660
        # = (1000/1M * 2.76) + (500/1M * 13.80)
        # = 0.00276 + 0.0069
        # = 0.00966
    """
    if model not in MODEL_PRICING:
        raise ValueError(
            f"Modello '{model}' non supportato. "
            f"Modelli disponibili: {list(MODEL_PRICING.keys())}"
        )

    pricing = MODEL_PRICING[model]
    cost = (tokens_in / 1_000_000 * pricing["input"]) + \
           (tokens_out / 1_000_000 * pricing["output"])
    return round(cost, 6)


def estimate_daily_cost(
    tasks_per_day: int,
    avg_tokens_in: int,
    avg_tokens_out: int,
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Stima il costo giornaliero per un agente.

    Args:
        tasks_per_day:  Numero medio di task al giorno.
        avg_tokens_in:  Token input medi per task.
        avg_tokens_out: Token output medi per task.
        model:          Modello utilizzato.

    Returns:
        Dict con {cost_per_task, daily_cost, monthly_estimate} in EUR.
    """
    cost_per_task = estimate_cost(avg_tokens_in, avg_tokens_out, model)
    daily = cost_per_task * tasks_per_day
    monthly = daily * 22  # giorni lavorativi

    return {
        "model": model,
        "cost_per_task_eur": cost_per_task,
        "daily_cost_eur": round(daily, 4),
        "monthly_estimate_eur": round(monthly, 2),
        "tasks_per_day": tasks_per_day,
    }


if __name__ == "__main__":
    # Esempio di utilizzo
    print("=== ProjectMultiAgentAI — Cost Estimator ===\n")

    # Stima per singola chiamata
    cost = estimate_cost(1000, 500, "claude-sonnet-4-6")
    print(f"Singola chiamata (1K in, 500 out, sonnet): EUR {cost}")

    # Stima giornaliera per sheets-agent
    daily = estimate_daily_cost(
        tasks_per_day=50,
        avg_tokens_in=200,
        avg_tokens_out=300,
        model="claude-haiku-4-5",
    )
    print(f"\nSheets Agent daily estimate: {daily}")
