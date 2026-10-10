"""STUB: hypothetical savings growth for the Future view.

Contract (docs/02-technical-spec.md, Analytics contracts):

    project(monthly_surplus_cents, years=10, rates={"low": 0.03, "mid": 0.06, "high": 0.08}) -> {
      "assumptions": {...rates used...}, "series": [{"year", "low_cents", "mid_cents", "high_cents"}]
    }   # rates are adjustable placeholders shown to the user, not advice

UI must label this "Hypothetical, not investment advice". Contributions are
made monthly and compounded annually; balances round to whole cents each year.
"""

from __future__ import annotations

from fractions import Fraction


def project(monthly_surplus_cents, years=10, rates={"low": 0.03, "mid": 0.06, "high": 0.08}):  # noqa: B006 (contract default; never mutated)
    used = {k: rates[k] for k in ("low", "mid", "high")}
    exact = {k: Fraction(str(v)) for k, v in used.items()}
    balances = {k: 0 for k in used}
    series = []
    for year in range(1, int(years) + 1):
        row = {"year": year}
        for k, rate in exact.items():
            grown = (balances[k] + 12 * int(monthly_surplus_cents)) * (1 + rate)
            balances[k] = round(grown)
            row[f"{k}_cents"] = balances[k]
        series.append(row)
    return {"assumptions": dict(used), "series": series}
