import { useState } from "react";

import {
  confirmRequirementReview,
  createRequirementReview,
  listRequirementVersions,
  RequirementAnalysis,
  updateAtomicRequirement,
  updateFinding,
  updateVisualInference,
} from "./api";

export function RequirementReviewPanel({ projectId }: { projectId: number }) {
  const [analysis, setAnalysis] = useState<RequirementAnalysis | null>(null);
  const [version, setVersion] = useState(1);
  const [confirmerName, setConfirmerName] = useState("测试工程师");
  const [error, setError] = useState("");

  const runReview = async () => {
    try {
      const versions = await listRequirementVersions(projectId);
      if (versions.length === 0) throw new Error("请先发布需求版本");
      setAnalysis(await createRequirementReview(projectId, version));
      setError("");
    } catch (reason) {
      setError(message(reason));
    }
  };

  const refresh = (request: Promise<RequirementAnalysis>) => {
    void request.then(setAnalysis).then(() => setError("")).catch((reason: unknown) => {
      setError(message(reason));
    });
  };

  return (
    <section className="panel">
      <h2>需求评审与确认</h2>
      {!analysis && <>
        <label>需求版本
          <input type="number" min="1" value={version} onChange={(event) => setVersion(Number(event.target.value))} />
        </label>
        <button onClick={() => void runReview()}>运行原子需求与需求评审</button>
      </>}
      {error && <p role="alert" className="error">{error}</p>}
      {analysis && <>
        <p>状态：{analysis.status === "confirmed" ? "需求已确认" : "等待测试工程师处理"}</p>
        <div className="requirement-summary">
          <h3>原子需求候选</h3>
          {analysis.atomic_requirements.map((candidate) => <article key={candidate.candidate_id}>
            <span>{candidate.statement}</span>
            <small>来源：{candidate.source_reference.filename} {candidate.source_reference.locator}</small>
            {candidate.decision === "pending_confirmation" && <div>
              <button onClick={() => refresh(updateAtomicRequirement(
                projectId, analysis.id, candidate.candidate_id, { decision: "accepted" },
              ))}>接受并获得稳定需求 ID</button>
              <button onClick={() => refresh(updateAtomicRequirement(
                projectId, analysis.id, candidate.candidate_id, { decision: "rejected" },
              ))}>拒绝</button>
            </div>}
            {candidate.stable_requirement_id && <small>稳定需求 ID：{candidate.stable_requirement_id}</small>}
          </article>)}
          <h3>需求评审发现</h3>
          {analysis.findings.map((finding) => <article key={finding.finding_id}>
            <span>{finding.summary}（{finding.finding_type}）</span>
            <small>{finding.reason} {finding.source_reference?.locator}</small>
            {finding.status === "pending_confirmation" && <div>
              <button onClick={() => refresh(updateFinding(
                projectId, analysis.id, finding.finding_id, "resolved",
              ))}>标记已解决</button>
              <button onClick={() => refresh(updateFinding(
                projectId, analysis.id, finding.finding_id, "rejected",
              ))}>拒绝发现</button>
            </div>}
          </article>)}
          {analysis.visual_inferences.map((inference) => <article key={inference.inference_id}>
            <span>视觉推断（待人工确认）：{inference.description}</span>
            <small>来源：{inference.source_reference.locator}</small>
            {inference.decision === "pending_confirmation" && <div>
              <button onClick={() => refresh(updateVisualInference(
                projectId, analysis.id, inference.inference_id, "accepted",
              ))}>
                接受为需求事实
              </button>
              <button onClick={() => refresh(updateVisualInference(
                projectId, analysis.id, inference.inference_id, "rejected",
              ))}>拒绝</button>
            </div>}
          </article>)}
        </div>
        {analysis.status === "draft" && <form className="project-form" onSubmit={(event) => {
          event.preventDefault();
          refresh(confirmRequirementReview(projectId, analysis.id, confirmerName));
        }}>
          <label>确认人名称<input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} /></label>
          <button type="submit">完成需求确认</button>
        </form>}
      </>}
    </section>
  );
}

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
