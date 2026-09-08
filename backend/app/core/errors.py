from __future__ import annotations


class AppError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class RecommendationNotFoundError(AppError):
    def __init__(self, recommendation_id: str) -> None:
        super().__init__(
            status_code=404,
            code="recommendation_not_found",
            message=f"Recommendation '{recommendation_id}' was not found.",
        )


class RecommendationDecisionNotFoundError(AppError):
    def __init__(self, decision_id: str) -> None:
        super().__init__(
            status_code=404,
            code="recommendation_decision_not_found",
            message=f"Recommendation decision '{decision_id}' was not found.",
        )


class RecommendationAuditNotAdoptableError(AppError):
    def __init__(self, recommendation_id: str) -> None:
        super().__init__(
            status_code=409,
            code="recommendation_audit_not_adoptable",
            message=(
                f"Recommendation '{recommendation_id}' has a critical audit status and "
                "cannot be marked adopted or partially adopted."
            ),
        )


class WeatherLocationConflictError(AppError):
    def __init__(self, location_id: str) -> None:
        super().__init__(
            status_code=409,
            code="weather_location_conflict",
            message=(
                f"Weather location '{location_id}' already exists with different coordinates "
                "or timezone."
            ),
        )


class WeatherProviderError(AppError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(
            status_code=502,
            code=code,
            message=message,
        )


class WeatherFeatureSnapshotNotFoundError(AppError):
    def __init__(self, identifier: str, *, identifier_type: str = "location") -> None:
        if identifier_type == "snapshot":
            message = f"Weather feature snapshot '{identifier}' was not found."
        else:
            message = f"No weather feature snapshot was found for location '{identifier}'."
        super().__init__(
            status_code=404,
            code="weather_feature_snapshot_not_found",
            message=message,
        )


class WeatherFeatureSnapshotNotUsableError(AppError):
    def __init__(self, snapshot_id: str, reason: str) -> None:
        super().__init__(
            status_code=409,
            code="weather_feature_snapshot_not_usable",
            message=f"Weather feature snapshot '{snapshot_id}' cannot be linked: {reason}.",
        )


class HydroOptimizationRunNotFoundError(AppError):
    def __init__(self, optimization_run_id: str) -> None:
        super().__init__(
            status_code=404,
            code="hydro_optimization_run_not_found",
            message=f"Hydro optimization run '{optimization_run_id}' was not found.",
        )


class HydroOptimizationRequestNotUsableError(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            status_code=409,
            code="hydro_optimization_request_not_usable",
            message=f"Hydro optimization request cannot be previewed: {reason}.",
        )


class MarketSourceEndpointNotFoundError(AppError):
    def __init__(self, endpoint_id: str) -> None:
        super().__init__(
            status_code=404,
            code="market_source_endpoint_not_found",
            message=f"Market source endpoint '{endpoint_id}' was not found.",
        )


class MarketEndpointProbeNotAllowedError(AppError):
    def __init__(self, endpoint_id: str, reason: str) -> None:
        super().__init__(
            status_code=409,
            code="market_endpoint_probe_not_allowed",
            message=f"Market source endpoint '{endpoint_id}' cannot be health checked: {reason}.",
        )


class MarketEndpointProbeRateLimitedError(AppError):
    def __init__(self, endpoint_id: str) -> None:
        super().__init__(
            status_code=429,
            code="market_endpoint_probe_rate_limited",
            message=f"Market source endpoint '{endpoint_id}' was health checked too recently.",
        )


class MarketArtifactRejectedError(AppError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(
            status_code=422,
            code=code,
            message=message,
        )


class MarketRawArtifactNotFoundError(AppError):
    def __init__(self, artifact_id: str) -> None:
        super().__init__(
            status_code=404,
            code="market_raw_artifact_not_found",
            message=f"Market raw artifact '{artifact_id}' was not found.",
        )


class MarketArtifactNotUsableError(AppError):
    def __init__(self, artifact_id: str, reason: str) -> None:
        super().__init__(
            status_code=409,
            code="market_artifact_not_usable",
            message=f"Market raw artifact '{artifact_id}' cannot be parsed: {reason}.",
        )


class MarketReportParsingError(AppError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(
            status_code=422,
            code=code,
            message=message,
        )


class ForecastResearchDatasetNotFoundError(AppError):
    def __init__(self, dataset_id: str) -> None:
        super().__init__(
            status_code=404,
            code="forecast_research_dataset_not_found",
            message=f"Forecast research dataset '{dataset_id}' was not found.",
        )


class ForecastResearchDatasetNotUsableError(AppError):
    def __init__(self, dataset_id: str, reason: str) -> None:
        super().__init__(
            status_code=409,
            code="forecast_research_dataset_not_usable",
            message=f"Forecast research dataset '{dataset_id}' cannot be backtested: {reason}.",
        )


class ForecastResearchModelRunNotFoundError(AppError):
    def __init__(self, model_run_id: str) -> None:
        super().__init__(
            status_code=404,
            code="forecast_research_model_run_not_found",
            message=f"Forecast research model run '{model_run_id}' was not found.",
        )


class ForecastResearchProviderError(AppError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(
            status_code=502,
            code=code,
            message=message,
        )


class OperationJobNotFoundError(AppError):
    def __init__(self, job_key: str) -> None:
        super().__init__(
            status_code=404,
            code="operation_job_not_found",
            message=f"Operation job '{job_key}' was not found.",
        )


class OperationJobManualTriggerDisabledError(AppError):
    def __init__(self, job_key: str) -> None:
        super().__init__(
            status_code=409,
            code="operation_job_manual_trigger_disabled",
            message=f"Operation job '{job_key}' cannot be triggered manually.",
        )


class WorkflowRunNotFoundError(AppError):
    def __init__(self, workflow_run_id: str) -> None:
        super().__init__(
            status_code=404,
            code="workflow_run_not_found",
            message=f"Workflow run '{workflow_run_id}' was not found.",
        )
