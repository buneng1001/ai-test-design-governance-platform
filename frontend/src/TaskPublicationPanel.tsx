import { FormEvent, useState } from "react";

import { publishTestTask, TestTask } from "./api";

interface Props {
  projectId: number;
}

export function TaskPublicationPanel({ projectId }: Props) {
  const [batchId, setBatchId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [target, setTarget] = useState<TestTask["execution_target"]>("unspecified");
  const [confirmerName, setConfirmerName] = useState("测试工程师");
  const [task, setTask] = useState<TestTask | null>(null);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setError("");
      setTask(await publishTestTask(projectId, Number(batchId), {
        confirmer_name: confirmerName,
        execution_target: target,
        stable_case_ids: [caseId],
        target_extension: {},
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "测试任务发布失败");
    }
  };

  return (
    <section className="panel">
      <h2>发布测试任务</h2>
      <p className="muted">仅能发布已完成用例确认的评审批次；目标扩展由执行适配器负责。</p>
      <form className="project-form" onSubmit={submit}>
        <label>
          评审批次 ID
          <input value={batchId} onChange={(event) => setBatchId(event.target.value)} required />
        </label>
        <label>稳定用例 ID<input value={caseId} onChange={(event) => setCaseId(event.target.value)} required /></label>
        <label>执行目标
          <select value={target} onChange={(event) => setTarget(event.target.value as TestTask["execution_target"])}>
            <option value="unspecified">暂未指定</option>
            <option value="manual">人工</option>
            <option value="test_execution_diagnostics">测试执行与诊断平台</option>
            <option value="generic_automation">通用自动化框架</option>
            <option value="external_executor">其他外部执行器</option>
          </select>
        </label>
        <label>
          确认人
          <input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} required />
        </label>
        <button type="submit">完成发布确认并生成任务</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {task && <p role="status">已生成 {task.contract_version}：{task.task_id}（{task.cases.length} 条用例）</p>}
    </section>
  );
}
