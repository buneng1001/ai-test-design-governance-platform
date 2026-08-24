import { useEffect, useState } from "react";

import { AIRun, listAIRuns } from "./api";

interface AIRunPanelProps {
  projectId: number;
}

export function AIRunPanel({ projectId }: AIRunPanelProps) {
  const [runs, setRuns] = useState<AIRun[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    listAIRuns(projectId).then(setRuns).catch(() => setError("AI 运行记录暂时不可用"));
  }, [projectId]);

  return (
    <section className="panel" aria-label="AI 运行审计">
      <h2>AI 运行审计</h2>
      <p>模型输出先经过结构校验；Mock 运行只用于离线演示和验证，不代表真实模型结果。</p>
      {error && <p role="alert" className="error">{error}</p>}
      {runs.length === 0 && !error && <p>当前项目还没有 AI 运行。</p>}
      {runs.length > 0 && (
        <div className="run-list">
          {runs.map((run) => (
            <article key={run.id}>
              <strong>{run.task_type}</strong>
              <span>{run.is_mock ? "Mock AI 运行" : "真实模型运行"}</span>
              <span>状态：{run.status} / 校验：{run.validation_status}</span>
              <span>尝试次数：{run.attempts.length} · Prompt 版本：{run.prompt_version}</span>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
