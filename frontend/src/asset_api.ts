// 资产领域请求。
import { request } from "./api_client";
import type { AssetProvenanceInput, AssetProvenanceRecord } from "./api_types";

export const listAssets = (projectId: number): Promise<AssetProvenanceRecord[]> =>
  request(`/api/projects/${projectId}/assets`);
export const createAsset = (projectId: number, asset: AssetProvenanceInput): Promise<AssetProvenanceRecord> =>
  request(`/api/projects/${projectId}/assets`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(asset),
  });
export const deleteAsset = (projectId: number, assetId: number): Promise<{ deleted: boolean }> => request(
  `/api/projects/${projectId}/assets/${assetId}`, { method: "DELETE" },
);
