import { useEffect, useState } from "react";

import {
  confirmTestPointReview, generateTestPointReview, getRequirementReview, RequirementAnalysis,
  TestPointReview, updateTestPointScope,
} from "./api";

export function TestPointReviewPanel({ projectId, analysisId, onWorkflowChanged }: {
  projectId: number;
  analysisId: number | null;
  onWorkflowChanged: () => void;
}) {
  const [analysis, setAnalysis] = useState<RequirementAnalysis | null>(null);
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  const [selectedPoints, setSelectedPoints] = useState<string[]>([]);
  const [confirmerName, setConfirmerName] = useState("测试工程师");
  const [error, setError] = useState("");
  const restoreSelection = (review: TestPointReview | null) => {
    setSelectedItems(review?.selected_test_item_ids ?? []);
    setSelectedPoints(review?.selected_test_point_ids ?? []);
  };

  useEffect(() => {
    if (!analysisId) return;
    void getRequirementReview(projectId, analysisId).then((result) => {
      setAnalysis(result);
      restoreSelection(result.test_point_review);
    }).catch((reason: unknown) => setError(message(reason)));
  }, [analysisId, projectId]);

  const update = (result: RequirementAnalysis) => {
    setAnalysis(result);
    restoreSelection(result.test_point_review);
    setError("");
    onWorkflowChanged();
  };
  const review = analysis?.test_point_review;
  const selectedCount = review ? review.test_points.filter((point) => (
    selectedItems.includes(point.test_item_id) || selectedPoints.includes(point.platform_test_point_id)
  )).length : 0;
  const saveSelection = async (): Promise<RequirementAnalysis> => {
    if (!analysis) throw new Error("请先生成测试点审核");
    const result = await updateTestPointScope(projectId, analysis.id, selectedItems, selectedPoints);
    update(result);
    return result;
  };
  const save = () => void saveSelection().catch((reason: unknown) => setError(message(reason)));
  const confirm = () => void (async () => {
    try {
      const saved = await saveSelection();
      update(await confirmTestPointReview(projectId, saved.id, confirmerName));
    } catch (reason) {
      setError(message(reason));
    }
  })();

  if (!analysisId) return <p className="muted">请先完成需求确认并生成新增建议。</p>;
  if (!analysis) return error ? <p role="alert" className="error">{error}</p> : <p className="muted">正在恢复测试点审核…</p>;
  if (!review) return <section aria-labelledby="test-point-review">
    <h3 id="test-point-review">Step 07–08 测试点审核与范围选择</h3>
    <p>将已确认需求组织为模块、测试项和测试点；待处置建议只会排除其关联范围。</p>
    <button onClick={() => void generateTestPointReview(projectId, analysis.id).then(update)
      .catch((reason: unknown) => setError(message(reason)))}>生成测试点审核</button>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;

  const locked = review.status === "confirmed";
  return <section aria-labelledby="test-point-review">
    <h3 id="test-point-review">Step 07–08 测试点审核与范围选择</h3>
    <p>需求模块 {review.modules.length} 个；测试项 {review.test_items.length} 个；测试点 {review.test_points.length} 个；预计用例 {selectedCount} 条。</p>
    <p role="status">覆盖自检：{review.coverage_check.passed ? "通过" : "未通过"}（需求 {review.coverage_check.covered_requirement_count}/{review.coverage_check.total_confirmed_requirement_count}）</p>
    {!review.coverage_check.passed && <p className="error">未覆盖需求：{review.coverage_check.uncovered_requirement_ids.join("、") || "无"}；孤立测试点：{review.coverage_check.isolated_test_point_ids.join("、") || "无"}</p>}
    {review.test_items.map((item) => <article className="suggestion-card" key={item.test_item_id}>
      <label className="checkbox-label"><input type="checkbox" disabled={locked} checked={selectedItems.includes(item.test_item_id)}
        onChange={() => setSelectedItems(toggle(selectedItems, item.test_item_id))} /><span>选择测试项：{item.name}（{item.module}）</span></label>
      <p>追溯需求：{item.stable_requirement_ids.join("、")}</p>
      {review.test_points.filter((point) => point.test_item_id === item.test_item_id).map((point) => <div key={point.platform_test_point_id}>
        <label className="checkbox-label"><input type="checkbox" disabled={locked} checked={selectedPoints.includes(point.platform_test_point_id)}
          onChange={() => setSelectedPoints(toggle(selectedPoints, point.platform_test_point_id))} /><span>{directionLabel(point.direction)}：{point.objective}</span></label>
        <details><summary>专家设计依据与追溯</summary><p>Skill 编号：{point.skill_test_point_id}；平台 ID：{point.platform_test_point_id}；规则：{point.rule_ids.join("、") || "未单列"}；来源：{point.source_references.map((source) => `${source.filename} ${source.locator}`).join("；")}</p></details>
      </div>)}
    </article>)}
    {!locked && <div className="button-group">
      <button onClick={save}>保存生成范围</button>
      <label>确认人名称<input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} /></label>
      <button onClick={confirm} disabled={!review.coverage_check.passed}>确认审核并固化交接</button>
    </div>}
    {locked && <p className="success">已确认交接版本：{review.handoff_version}；已选择 {selectedCount} 个测试点。</p>}
    <a href={`/api/projects/${projectId}/requirement-reviews/${analysis.id}/step-00-08-package.md`}>导出 Step 00–08 兼容 Markdown 分析包</a>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const toggle = (items: string[], item: string) => items.includes(item)
  ? items.filter((value) => value !== item) : [...items, item];
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
const directionLabel = (direction: string): string => ({ normal: "正常", exception: "异常", boundary: "边界", risk: "风险", permission: "权限" })[direction] ?? direction;
