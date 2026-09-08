# Workers

Prefect runs local workstation background jobs for public data ingestion,
parsing, feature generation, research backtests, and daily brief generation.

The API database remains the business audit source of truth. Prefect state is
supplementary orchestration metadata.

`python -m workers.scheduled` registers long-lived local static deployments
for the fixed workstation job registry. Scheduled runs write auditable queued
records only.

`python -m workers.consume` leases PostgreSQL workflow records and executes
only fixed registered handlers. It never accepts a URL, command, or dynamic
import path. Expired leases can be recovered by another worker. Adapter-level
bounded retries remain in place; transient workflow failures wait and retry at
most once. The daily brief schedule checks the persisted mainland workday
calendar before queueing a run.

Scheduled records use the Prefect planned start time as an idempotency key.
Consumers renew active leases while handlers run. Recovery rotates an internal
lease token so a stale worker cannot overwrite the current owner. A workflow
fails as `workflow_lease_exhausted` after the allowed recovery attempt expires.
