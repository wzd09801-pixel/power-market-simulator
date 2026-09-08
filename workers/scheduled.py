from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from prefect import flow, get_run_logger, serve
from prefect.runtime import flow_run
from prefect.schedules import Cron

from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.services.operations import queue_scheduled_operation_job

TIMEZONE = "Asia/Shanghai"


def _queue(job_key: str) -> None:
    logger = get_run_logger()
    settings = get_settings()
    factory = get_session_factory(settings.database_url)
    prefect_flow_run_id = str(flow_run.id) if flow_run.id is not None else None
    scheduled_for = flow_run.scheduled_start_time or datetime.now(tz=ZoneInfo(TIMEZONE))
    with factory() as session:
        queued = queue_scheduled_operation_job(
            job_key,
            scheduled_for=scheduled_for,
            prefect_flow_run_id=prefect_flow_run_id,
            session=session,
        )
    if queued is None:
        logger.info("Skipped %s because the local date is not a mainland workday.", job_key)
    else:
        logger.info("Queued fixed workstation job %s as %s.", job_key, queued.workflow_run_id)


@flow(name="weather-refresh-schedule")
def weather_refresh_schedule() -> None:
    _queue("weather_refresh")


@flow(name="policy-research-refresh-schedule")
def policy_research_refresh_schedule() -> None:
    _queue("policy_research_refresh")


@flow(name="bench-dispatch-research-schedule")
def bench_dispatch_research_schedule() -> None:
    _queue("bench_dispatch_research")


@flow(name="daily-intelligence-brief-schedule")
def daily_intelligence_brief_schedule() -> None:
    _queue("daily_intelligence_brief")


def main() -> None:
    serve(
        weather_refresh_schedule.to_deployment(
            name="weather-refresh",
            schedules=[Cron("0 7,16 * * *", timezone=TIMEZONE)],
        ),
        policy_research_refresh_schedule.to_deployment(
            name="policy-research-refresh",
            schedules=[Cron("0 1,7,13,19 * * *", timezone=TIMEZONE)],
        ),
        bench_dispatch_research_schedule.to_deployment(
            name="bench-dispatch-research",
            schedules=[Cron("30 9 * * *", timezone=TIMEZONE)],
        ),
        daily_intelligence_brief_schedule.to_deployment(
            name="daily-intelligence-brief",
            schedules=[Cron("30 8 * * *", timezone=TIMEZONE)],
        ),
    )


if __name__ == "__main__":
    main()
