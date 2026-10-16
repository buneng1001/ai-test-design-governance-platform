import type { RunEvidence, RunPage, WorkspaceState } from "./v020_types";

export function visibleRunForPage(workspace: WorkspaceState, page: RunPage): RunEvidence | undefined {
  const latestAttempt = [...workspace.runs].reverse().find((run) => run.page === page);
  if (latestAttempt?.status === "failed" || latestAttempt?.status === "running") return latestAttempt;
  const activeId = workspace.active_run_ids?.[page];
  return workspace.runs.find((run) => run.id === activeId) ?? latestAttempt;
}
