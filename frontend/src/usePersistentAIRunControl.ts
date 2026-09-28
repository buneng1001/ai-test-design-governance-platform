import { useCallback, useEffect, useState } from "react";

import { getAIRunControl } from "./ai_api";
import type { AIRunControl } from "./api_types_ai";

/**
 * 只保存运行标识，服务端仍是运行状态和检查点的唯一来源。
 * 因此刷新页面或浏览器重启后不会丢失可继续的运行。
 */
export function usePersistentAIRunControl(projectId: number, scope: string) {
  const storageKey = `ai-run-control:${projectId}:${scope}`;
  const [runControl, setRunControl] = useState<AIRunControl | null>(null);

  const remember = useCallback((control: AIRunControl | null) => {
    setRunControl(control);
    if (control) localStorage.setItem(storageKey, control.id);
    else localStorage.removeItem(storageKey);
  }, [storageKey]);

  const refresh = useCallback(async () => {
    const runId = runControl?.id ?? localStorage.getItem(storageKey);
    if (!runId) return null;
    const control = await getAIRunControl(projectId, runId);
    remember(control);
    return control;
  }, [projectId, remember, runControl?.id, storageKey]);

  // 仅在工作流范围改变（或页面首次载入）时恢复。不能依赖 runControl，
  // 否则刚创建运行后会额外轮询一次，抢占下一次“执行一批”的请求。
  useEffect(() => {
    const runId = localStorage.getItem(storageKey);
    if (!runId) return;
    void getAIRunControl(projectId, runId).then(remember).catch(() => localStorage.removeItem(storageKey));
  }, [projectId, remember, storageKey]);
  useEffect(() => {
    if (!runControl || runControl.status === "completed") return undefined;
    const timer = window.setInterval(() => { void refresh().catch(() => undefined); }, 1500);
    return () => window.clearInterval(timer);
  }, [refresh, runControl]);

  return { runControl, remember, refresh };
}
