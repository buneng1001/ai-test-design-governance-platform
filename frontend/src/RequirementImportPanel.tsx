import { FormEvent, useEffect, useState } from "react";

import {
  createRequirementPackage,
  listAssets,
  listRequirementVersions,
  publishRequirementPackage,
  RequirementFileInput,
  RequirementPackage,
  RequirementVersion,
} from "./api";


export function RequirementImportPanel({ projectId }: { projectId: number }) {
  const [assets, setAssets] = useState<Awaited<ReturnType<typeof listAssets>>>([]);
  const [selectedAssetIds, setSelectedAssetIds] = useState<number[]>([]);
  const [files, setFiles] = useState<RequirementFileInput[]>([]);
  const [draft, setDraft] = useState<RequirementPackage | null>(null);
  const [versions, setVersions] = useState<RequirementVersion[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void listRequirementVersions(projectId).then(setVersions).catch((reason: unknown) => setError(message(reason)));
  }, [projectId]);

  useEffect(() => {
    void listAssets(projectId).then(setAssets).catch((reason: unknown) => setError(message(reason)));
  }, [projectId]);

  const inspect = async (event: FormEvent) => {
    event.preventDefault();
    if (selectedAssetIds.length === 0) {
      setError("请选择当前任务使用的已登记需求资料");
      return;
    }
    try {
      const fileInputs = buildFileInputs(selectedAssetIds, assets);
      setFiles(fileInputs);
      setDraft(await createRequirementPackage(projectId, "当前任务", fileInputs));
      setError("");
    } catch (reason) {
      setError(message(reason));
    }
  };

  const publish = async () => {
    if (!draft) return;
    try {
      const version = await publishRequirementPackage(projectId, draft.id);
      setVersions([...versions, version]);
      setDraft({ ...draft, status: "published", published_version_id: version.id });
      setError("");
    } catch (reason) {
      setError(message(reason));
    }
  };

  return (
    <section className="panel">
      <h2>导入需求资料</h2>
      <p>先登记资产来源，再选择同名文件组成需求资料包；发布后会形成不可覆盖的需求版本。</p>
      <form className="project-form" onSubmit={inspect}>
        <label>
          当前任务使用的文件
          <span className="asset-checklist">{assets
            .filter((asset) => asset.asset_type === "requirement_material" && asset.can_enter_requirement_package)
            .map((asset) => <label key={asset.id}><input type="checkbox" checked={selectedAssetIds.includes(asset.id)}
              onChange={(event) => setSelectedAssetIds(event.target.checked
                ? [...selectedAssetIds, asset.id]
                : selectedAssetIds.filter((id) => id !== asset.id))} />{asset.name}</label>)}</span>
        </label>
        {files.length > 0 && <p>已选择：{files.map((file) => file.filename).join("、")}</p>}
        <button type="submit">查看解析结果</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {draft && <div className="requirement-summary">
        <h3>发布前资料包清单</h3>
        {draft.materials.map((material) => <article key={material.asset_id}>
          <strong>{material.filename}</strong>
          <span>{statusLabel(material.parse_status)} · {material.format} · {material.fragments.length} 个来源片段</span>
          {material.fragments.length > 0 && <details>
            <summary>查看解析结果与来源位置</summary>
            <ul>
              {material.fragments.map((fragment) => <li key={fragment.source_reference.reference_id}>
                <code>{fragment.source_reference.locator}</code>：{fragment.text}
              </li>)}
            </ul>
          </details>}
          {material.visual_inferences.map((candidate) => (
            <p key={candidate.source_reference.reference_id}>
            视觉推断（待人工确认）：{candidate.description}；来源：{candidate.source_reference.locator}
            </p>
          ))}
          {material.diagnostics.map((diagnostic) => <p className="error" key={diagnostic.code}>
            {diagnostic.message}
          </p>)}
        </article>)}
        <button disabled={draft.status === "published"} onClick={() => void publish()}>
          {draft.status === "published" ? "已发布需求版本" : "发布需求版本"}
        </button>
      </div>}
      <div className="version-list" aria-label="需求版本列表">
        {versions.map((version) => <article key={version.id}>
          <strong>V{version.version} · {version.name}</strong>
          <span>{version.materials.map((material) =>
            `${material.filename}：${statusLabel(material.parse_status)}（${material.format}）`
          ).join("；")}</span>
        </article>)}
      </div>
    </section>
  );
}

const statusLabel = (status: RequirementPackage["materials"][number]["parse_status"]): string => ({
  complete: "解析完整",
  partial: "部分解析",
  failed: "解析失败",
  rejected: "已拒绝",
})[status];

const buildFileInputs = (assetIds: number[], assets: Awaited<ReturnType<typeof listAssets>>): RequirementFileInput[] =>
  assetIds.map((assetId) => {
    const asset = assets.find((item) => item.id === assetId);
    return {
          asset_id: assetId, filename: asset?.name ?? "需求资料", media_type: asset?.media_type ?? "application/octet-stream", content_base64: "",
    };
  });

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
