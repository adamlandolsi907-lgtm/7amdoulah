"""
Energy consumption forecasting.

Tries Prophet (1.1+) first; falls back to statsmodels Holt-Winters if unavailable.
NOTE: ~12 monthly data points is the minimum for seasonal patterns.
      Confidence intervals are intentionally wide to reflect limited data.
"""

import warnings
import statistics
from typing import Optional

from app.models.schemas import EnergyRecord, EnergyType, ForecastPoint, ForecastResult


def _next_months(last_date: str, n: int) -> list[str]:
    """Generate n month strings after last_date (YYYY-MM)."""
    import datetime
    last = datetime.datetime.strptime(last_date + "-01", "%Y-%m-%d")
    out = []
    for i in range(1, n + 1):
        month = (last.month - 1 + i) % 12 + 1
        year = last.year + ((last.month - 1 + i) // 12)
        out.append(f"{year}-{month:02d}")
    return out


def _naive_forecast(
    values: list[float],
    dates: list[str],
    horizon: int,
) -> list[ForecastPoint]:
    """Simple mean ± 1.96σ fallback — used when no model is available."""
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else mean * 0.15
    future_dates = _next_months(dates[-1], horizon)
    return [
        ForecastPoint(
            date=d,
            predicted_kwh=round(max(0.0, mean), 1),
            lower_bound=round(max(0.0, mean - 1.96 * std), 1),
            upper_bound=round(mean + 1.96 * std, 1),
        )
        for d in future_dates
    ]


def _holtwinters_forecast(
    values: list[float],
    dates: list[str],
    horizon: int,
) -> tuple[list[ForecastPoint], str]:
    """Holt-Winters exponential smoothing via statsmodels."""
    try:
        import datetime
        import pandas as pd
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        ds = [datetime.datetime.strptime(d + "-01", "%Y-%m-%d") for d in dates]
        series = pd.Series(values, index=pd.DatetimeIndex(ds, freq="MS"))

        sp = min(12, len(values) // 2)
        use_seasonal = len(values) >= 2 * sp
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal="add" if use_seasonal else None,
                seasonal_periods=sp if use_seasonal else None,
            )
            fit = model.fit(optimized=True, use_brute=False)

        forecast_vals = list(fit.forecast(horizon))
        std = statistics.stdev(values) if len(values) > 1 else statistics.mean(values) * 0.15
        future_dates = _next_months(dates[-1], horizon)

        points = []
        for i, (d, v) in enumerate(zip(future_dates, forecast_vals)):
            margin = std * (1.0 + i * 0.15)
            points.append(ForecastPoint(
                date=d,
                predicted_kwh=round(max(0.0, v), 1),
                lower_bound=round(max(0.0, v - 1.96 * margin), 1),
                upper_bound=round(v + 1.96 * margin, 1),
            ))
        return points, "holt_winters"
    except Exception:
        return _naive_forecast(values, dates, horizon), "naive_mean"


def _prophet_forecast(
    values: list[float],
    dates: list[str],
    horizon: int,
) -> tuple[list[ForecastPoint], str]:
    """Prophet-based forecast with yearly seasonality."""
    try:
        import datetime
        import pandas as pd
        from prophet import Prophet

        ds = [datetime.datetime.strptime(d + "-01", "%Y-%m-%d") for d in dates]
        df = pd.DataFrame({"ds": ds, "y": values})

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = Prophet(
                yearly_seasonality=len(values) >= 12,
                weekly_seasonality=False,
                daily_seasonality=False,
                interval_width=0.90,
                seasonality_mode="multiplicative" if len(values) >= 12 else "additive",
            )
            m.fit(df)

        future = m.make_future_dataframe(periods=horizon, freq="MS")
        forecast_df = m.predict(future)
        future_rows = forecast_df.tail(horizon)

        points = [
            ForecastPoint(
                date=row["ds"].strftime("%Y-%m"),
                predicted_kwh=round(max(0.0, row["yhat"]), 1),
                lower_bound=round(max(0.0, row["yhat_lower"]), 1),
                upper_bound=round(row["yhat_upper"], 1),
            )
            for _, row in future_rows.iterrows()
        ]
        return points, "prophet"
    except Exception:
        return _holtwinters_forecast(values, dates, horizon)


def forecast(
    records: list[EnergyRecord],
    zone: str = "global",
    energy_type: EnergyType = EnergyType.electricity,
    horizon: int = 3,
) -> Optional[ForecastResult]:
    """
    Forecast energy consumption. Returns None if <4 data points.

    Tries Prophet → Holt-Winters → naive mean in that order.
    """
    filtered = [
        r for r in records
        if (zone == "global" or r.zone == zone)
        and r.energy_type == energy_type
        and r.quantity_kwh is not None
        and r.quantity_kwh > 0
    ]
    if len(filtered) < 4:
        return None

    # Aggregate by month
    by_date: dict[str, float] = {}
    for r in sorted(filtered, key=lambda x: x.date):
        by_date[r.date] = by_date.get(r.date, 0.0) + (r.quantity_kwh or 0.0)

    dates = sorted(by_date.keys())
    values = [by_date[d] for d in dates]

    points, model_used = _prophet_forecast(values, dates, horizon)

    return ForecastResult(
        zone=zone,
        energy_type=energy_type,
        horizon_months=horizon,
        points=points,
        model_used=model_used,
    )
