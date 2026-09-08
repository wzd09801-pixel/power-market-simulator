---
name: forecasting-model
description: Use when implementing electricity price forecasting, feature engineering, weather features, 96-point trend detection, backtesting, model registry, metrics, or forecast evaluation for this project.
---

# Forecasting Model

Forecasting must start with simple baselines before complex models.

## Targets

Default targets:

- 96-point day-ahead price trend when data supports it.
- Daily or aggregate market trend when only aggregate data is available.
- q10, q50, q90 intervals when feasible.
- Peak-valley spread.
- High-price and low-price window detection.

## Model Order

1. Seasonal naive baseline.
2. Rolling or calendar baseline.
3. LightGBM or XGBoost.
4. Quantile model.
5. Ensemble only after individual models are measured.

Do not start with deep learning or reinforcement learning in the MVP.

## Metrics

Always calculate where applicable:

- MAE
- RMSE
- sMAPE or MAPE when denominator is safe
- peak-period MAE
- valley-period MAE
- direction accuracy
- high-price-window recall

## Registry Fields

Every saved model must record:

- model name and version
- train start and end
- feature version
- metrics JSON
- artifact path
- status: candidate, production, or archived

Never automatically promote a model to production.
