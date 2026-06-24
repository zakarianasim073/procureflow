def line_total(quantity: float, rate: float) -> float:
    return round(quantity * rate, 2)


def variance(a: float, b: float) -> float:
    return round(b - a, 2)


def pct_variance(boq_rate: float, sor_rate: float) -> float:
    if not sor_rate:
        return 0.0
    return round(((boq_rate - sor_rate) / sor_rate) * 100, 2)


def flag_status(pct: float | None, sor_rate: float | None, boq_rate: float | None) -> str:
    if sor_rate is None:
        return "SOR missing"
    if boq_rate is None:
        return "BOQ rate missing"
    if pct is None:
        return "OK"
    if abs(pct) > 10:
        return "MISMATCH"
    if abs(pct) > 0:
        return "VARIANCE"
    return "OK"
