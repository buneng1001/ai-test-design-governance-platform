// 测试设计领域请求。
import { request } from "./api_client";
import type { TestDesign } from "./api_types";

export const createTestDesign = (projectId: number, versionId: number): Promise<TestDesign> => request(
  `/api/projects/${projectId}/requirement-versions/${versionId}/test-designs`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) },
);
export const confirmTestDesign = (projectId: number, designId: number, confirmerName: string): Promise<TestDesign> =>
  request(`/api/projects/${projectId}/test-designs/${designId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmer_name: confirmerName }),
  });
export const addTestDimension = (projectId: number, designId: number, name: string): Promise<TestDesign> =>
  request(`/api/projects/${projectId}/test-designs/${designId}/dimensions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  });
export const adjustTestRisk = (projectId: number, designId: number, scopeItemId: string,
  factors: TestDesign["risks"][number]["factors"]): Promise<TestDesign> =>
  request(`/api/projects/${projectId}/test-designs/${designId}/risks/${scopeItemId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ factors, adjustment_reason: "测试工程师在页面确认风险因子" }),
  });
export const decideAutomation = (projectId: number, designId: number, scopeItemId: string,
  factors: TestDesign["automation_candidates"][number]["factors"], decision: string): Promise<TestDesign> =>
  request(`/api/projects/${projectId}/test-designs/${designId}/automation/${scopeItemId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ factors, decision, decision_reason: "测试工程师在页面确认自动化决定" }),
  });
