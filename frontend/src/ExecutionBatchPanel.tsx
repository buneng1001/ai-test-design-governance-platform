import { FormEvent, useState } from "react";

import { createExecutionBatch, downloadManualExecutionFile, ExecutionBatch } from "./api";

interface Props {
  projectId: number;
}

export function ExecutionBatchPanel({ projectId }: Props) {
  const [taskId, setTaskId] = useState("");
  const [requirementVersionId, setRequirementVersionId] = useState("");
  const [caseIds, setCaseIds] = useState("");
  const [productVersion, setProductVersion] = useState("");
  const [environment, setEnvironment] = useState("");
  const [scope, setScope] = useState("");
  const [responsiblePerson, setResponsiblePerson] = useState("测试工程师");
  const [batch, setBatch] = useState<ExecutionBatch | null>(null);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setError("");
      const created = await createExecutionBatch(projectId, taskId, {
        product_version: productVersion,
        requirement_version_id: Number(requirementVersionId),
        environment,
        scope,
        responsible_person: responsiblePerson,
        stable_case_ids: caseIds.split("\n").map((id) => id.trim()).filter(Boolean),
      });
      setBatch(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "执行批次创建失败");
    }
  };

  return (
    <section className="panel">
      <h2>创建执行批次</h2>
      <p className="muted">从已发布测试任务选择稳定用例，冻结本轮上下文并生成供人工填写的执行文件。</p>
      <form className="project-form" onSubmit={submit}>
        <label>测试任务 ID<input value={taskId} onChange={(event) => setTaskId(event.target.value)} required /></label>
        <label>
          需求版本 ID
          <input type="number" min="1" value={requirementVersionId}
            onChange={(event) => setRequirementVersionId(event.target.value)} required />
        </label>
        <label>
          选择稳定用例 ID（每行一个）
          <textarea value={caseIds} onChange={(event) => setCaseIds(event.target.value)} required />
        </label>
        <label>
          产品版本
          <input value={productVersion} onChange={(event) => setProductVersion(event.target.value)} required />
        </label>
        <label>环境<input value={environment} onChange={(event) => setEnvironment(event.target.value)} required /></label>
        <label>测试范围<input value={scope} onChange={(event) => setScope(event.target.value)} required /></label>
        <label>
          负责人
          <input value={responsiblePerson} onChange={(event) => setResponsiblePerson(event.target.value)} required />
        </label>
        <button type="submit">创建执行批次</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {batch && <p role="status">
        执行批次 {batch.id} 已创建，已冻结 {batch.cases.length} 条用例。
        <button type="button" onClick={() => void downloadManualExecutionFile(projectId, batch.id)}>
          下载人工执行文件
        </button>
      </p>}
    </section>
  );
}
