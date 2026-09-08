import type { WorkflowRun } from "./types";

export function nextPollDelayMilliseconds(run: WorkflowRun, now = Date.now()) {
  if (run.status !== "retry_wait") return 750;
  const availableAt = Date.parse(run.available_at);
  return Number.isNaN(availableAt) ? 750 : Math.min(Math.max(availableAt - now, 750), 5_000);
}
