from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import sqrt
from statistics import mean

INTERVALS_PER_DAY = 96
MODEL_VERSION = "v1"
FEATURE_VERSION = "interval_price_v1"


@dataclass(frozen=True)
class ResearchPricePoint:
    interval_start: datetime
    trade_date: date
    interval_index: int
    price: Decimal


@dataclass(frozen=True)
class ResearchPrediction:
    target_interval_start: datetime
    trade_date: date
    interval_index: int
    actual_price: Decimal
    predicted_price: Decimal


@dataclass(frozen=True)
class ResearchBacktestResult:
    predictions: tuple[ResearchPrediction, ...]
    train_start: date
    train_end: date
    evaluation_start: date
    evaluation_end: date
    parameters: dict[str, object]
    metrics: dict[str, object]


class InsufficientResearchHistoryError(ValueError):
    pass


def run_research_backtest(
    points: list[ResearchPricePoint],
    *,
    model_key: str,
    evaluation_days: int,
    lag_days: int,
    lookback_days: int,
) -> ResearchBacktestResult:
    by_date = _group_complete_days(points)
    if model_key == "seasonal_naive":
        predictions, evaluation_dates, history_dates = _seasonal_naive_predictions(
            by_date,
            evaluation_days=evaluation_days,
            lag_days=lag_days,
        )
        parameters: dict[str, object] = {
            "evaluation_days": evaluation_days,
            "lag_days": lag_days,
        }
    elif model_key == "calendar_mean":
        predictions, evaluation_dates, history_dates = _calendar_mean_predictions(
            by_date,
            evaluation_days=evaluation_days,
            lookback_days=lookback_days,
        )
        parameters = {
            "evaluation_days": evaluation_days,
            "lookback_days": lookback_days,
        }
    else:
        raise ValueError(f"Unsupported research model '{model_key}'.")

    train_start = min(history_dates)
    evaluation_start = min(evaluation_dates)
    return ResearchBacktestResult(
        predictions=tuple(predictions),
        train_start=train_start,
        train_end=evaluation_start - timedelta(days=1),
        evaluation_start=evaluation_start,
        evaluation_end=max(evaluation_dates),
        parameters=parameters,
        metrics=_calculate_metrics(predictions),
    )


def _group_complete_days(
    points: list[ResearchPricePoint],
) -> dict[date, tuple[ResearchPricePoint, ...]]:
    grouped: dict[date, list[ResearchPricePoint]] = {}
    for point in points:
        grouped.setdefault(point.trade_date, []).append(point)
    complete: dict[date, tuple[ResearchPricePoint, ...]] = {}
    for trade_date, daily_points in grouped.items():
        ordered = tuple(sorted(daily_points, key=lambda item: item.interval_index))
        if len(ordered) != INTERVALS_PER_DAY:
            continue
        if [item.interval_index for item in ordered] != list(range(1, INTERVALS_PER_DAY + 1)):
            continue
        complete[trade_date] = ordered
    return complete


def _seasonal_naive_predictions(
    by_date: dict[date, tuple[ResearchPricePoint, ...]],
    *,
    evaluation_days: int,
    lag_days: int,
) -> tuple[list[ResearchPrediction], list[date], list[date]]:
    eligible_dates = sorted(
        trade_date for trade_date in by_date if trade_date - timedelta(days=lag_days) in by_date
    )
    selected_dates = _select_evaluation_dates(eligible_dates, evaluation_days)
    history_dates = [trade_date - timedelta(days=lag_days) for trade_date in selected_dates]
    predictions = [
        _to_prediction(actual, previous.price)
        for trade_date in selected_dates
        for actual, previous in zip(
            by_date[trade_date],
            by_date[trade_date - timedelta(days=lag_days)],
            strict=True,
        )
    ]
    return predictions, selected_dates, history_dates


def _calendar_mean_predictions(
    by_date: dict[date, tuple[ResearchPricePoint, ...]],
    *,
    evaluation_days: int,
    lookback_days: int,
) -> tuple[list[ResearchPrediction], list[date], list[date]]:
    history_by_date: dict[date, list[date]] = {}
    for trade_date in sorted(by_date):
        history_dates = [
            trade_date - timedelta(days=offset)
            for offset in range(1, lookback_days + 1)
            if trade_date - timedelta(days=offset) in by_date
        ]
        if len(history_dates) >= 2:
            history_by_date[trade_date] = history_dates
    selected_dates = _select_evaluation_dates(sorted(history_by_date), evaluation_days)
    used_history = sorted(
        {
            history_date
            for trade_date in selected_dates
            for history_date in history_by_date[trade_date]
        }
    )
    predictions: list[ResearchPrediction] = []
    for trade_date in selected_dates:
        daily_history = history_by_date[trade_date]
        for actual in by_date[trade_date]:
            average_price = mean(
                by_date[history_date][actual.interval_index - 1].price
                for history_date in daily_history
            )
            predictions.append(_to_prediction(actual, average_price))
    return predictions, selected_dates, used_history


def _select_evaluation_dates(eligible_dates: list[date], evaluation_days: int) -> list[date]:
    if len(eligible_dates) < evaluation_days:
        raise InsufficientResearchHistoryError(
            f"At least {evaluation_days} eligible evaluation days are required; "
            f"found {len(eligible_dates)}."
        )
    return eligible_dates[-evaluation_days:]


def _to_prediction(actual: ResearchPricePoint, predicted_price: Decimal) -> ResearchPrediction:
    return ResearchPrediction(
        target_interval_start=actual.interval_start,
        trade_date=actual.trade_date,
        interval_index=actual.interval_index,
        actual_price=actual.price,
        predicted_price=predicted_price,
    )


def _calculate_metrics(predictions: list[ResearchPrediction]) -> dict[str, object]:
    actual = [float(item.actual_price) for item in predictions]
    predicted = [float(item.predicted_price) for item in predictions]
    absolute_errors = [
        abs(observed - forecast) for observed, forecast in zip(actual, predicted, strict=True)
    ]
    squared_errors = [
        (observed - forecast) ** 2 for observed, forecast in zip(actual, predicted, strict=True)
    ]
    smape_terms = [
        0.0
        if abs(observed) + abs(forecast) == 0
        else 2 * abs(observed - forecast) / (abs(observed) + abs(forecast))
        for observed, forecast in zip(actual, predicted, strict=True)
    ]
    daily_predictions = _group_predictions_by_date(predictions)
    return {
        "mae": _round(mean(absolute_errors)),
        "rmse": _round(sqrt(mean(squared_errors))),
        "smape": _round(mean(smape_terms)),
        "peak_period_mae": _round(_period_mae(daily_predictions, high=True)),
        "valley_period_mae": _round(_period_mae(daily_predictions, high=False)),
        "direction_accuracy": _round(_direction_accuracy(daily_predictions)),
        "high_price_window_recall": _round(_high_price_window_recall(daily_predictions)),
        "peak_valley_spread_mae": _round(_peak_valley_spread_mae(daily_predictions)),
        "prediction_count": len(predictions),
    }


def _group_predictions_by_date(
    predictions: list[ResearchPrediction],
) -> dict[date, tuple[ResearchPrediction, ...]]:
    grouped: dict[date, list[ResearchPrediction]] = {}
    for prediction in predictions:
        grouped.setdefault(prediction.trade_date, []).append(prediction)
    return {
        trade_date: tuple(sorted(items, key=lambda item: item.interval_index))
        for trade_date, items in grouped.items()
    }


def _period_mae(
    daily_predictions: dict[date, tuple[ResearchPrediction, ...]], *, high: bool
) -> float:
    errors: list[float] = []
    for predictions in daily_predictions.values():
        ranked = sorted(predictions, key=lambda item: item.actual_price)
        selected = ranked[-24:] if high else ranked[:24]
        errors.extend(abs(float(item.actual_price - item.predicted_price)) for item in selected)
    return mean(errors)


def _direction_accuracy(daily_predictions: dict[date, tuple[ResearchPrediction, ...]]) -> float:
    matches = 0
    comparisons = 0
    for predictions in daily_predictions.values():
        for previous, current in zip(predictions, predictions[1:], strict=False):
            observed_direction = _sign(current.actual_price - previous.actual_price)
            predicted_direction = _sign(current.predicted_price - previous.predicted_price)
            matches += observed_direction == predicted_direction
            comparisons += 1
    return matches / comparisons


def _high_price_window_recall(
    daily_predictions: dict[date, tuple[ResearchPrediction, ...]],
) -> float:
    recalls: list[float] = []
    for predictions in daily_predictions.values():
        observed_top = {
            item.interval_index
            for item in sorted(predictions, key=lambda item: item.actual_price)[-8:]
        }
        predicted_top = {
            item.interval_index
            for item in sorted(predictions, key=lambda item: item.predicted_price)[-8:]
        }
        recalls.append(len(observed_top & predicted_top) / len(observed_top))
    return mean(recalls)


def _peak_valley_spread_mae(
    daily_predictions: dict[date, tuple[ResearchPrediction, ...]],
) -> float:
    errors: list[float] = []
    for predictions in daily_predictions.values():
        actual_prices = [float(item.actual_price) for item in predictions]
        predicted_prices = [float(item.predicted_price) for item in predictions]
        actual_spread = max(actual_prices) - min(actual_prices)
        predicted_spread = max(predicted_prices) - min(predicted_prices)
        errors.append(abs(actual_spread - predicted_spread))
    return mean(errors)


def _sign(value: Decimal) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _round(value: float) -> float:
    return round(value, 6)
