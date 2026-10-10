import { ChangeEvent, useState } from "react";

import { RequirementMaterialStructure } from "./RequirementMaterialStructure";
import { downloadPageResult, uploadAndParseMaterials } from "./v020_api";
import type { WorkspaceState } from "./v020_types";

const supportedFormats = ".md,.txt,.json,.yaml,.yml,.docx,.pdf,.png,.jpg,.jpeg";

export function UploadWorkspace({ projectId, workspace, onChanged }: {
  projectId: number; workspace: WorkspaceState; onChanged: () => Promise<void>;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [notes, setNotes] = useState(workspace.supplemental_notes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const upload = async () => {
    if (!files.length) { setError("请选择至少一份资料"); return; }
    setBusy(true); setError("");
    try {
      await uploadAndParseMaterials(projectId, notes, await Promise.all(files.map(async (file) => ({
        filename: file.name, media_type: file.type || "application/octet-stream", content_base64: await toBase64(file),
      }))));
      await onChanged();
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  };
  const version = workspace.requirement_version;
  const parsedMaterials = workspace.parse_result?.materials ?? version?.materials ?? [];
  return <section className="workflow-page">
    <PageHeader title="上传文档" subtitle="上传并解析后直接核对章节、表格、正文片段与失败原因。" badge="本页面不调用 AI" />
    <label className="field-stack">补充说明（可选）<textarea value={notes} maxLength={4000}
      placeholder="例如：重点关注状态切换；历史版本章节不在本次范围。"
      onChange={(event) => setNotes(event.target.value)} /></label>
    <label className="file-picker">选择文件<input aria-label="需求文件" type="file" multiple accept={supportedFormats}
      onChange={(event: ChangeEvent<HTMLInputElement>) => setFiles(Array.from(event.target.files ?? []))} /></label>
    {files.length > 0 && <ul className="compact-list">{files.map((file) =>
      <li key={`${file.name}-${file.size}`}>{file.name} · {formatBytes(file.size)}</li>)}</ul>}
    <div className="action-row"><button type="button" disabled={busy} onClick={() => void upload()}>
      {busy ? "正在上传并解析…" : "上传并解析"}</button>
      <span>支持 Excel 用例模板以外的需求资料格式：PDF、Word、Markdown、文本、JSON/YAML 和图片。</span></div>
    {error && <p role="alert" className="error">{error}</p>}
    <section className="result-card" aria-label="文档解析结果">
      <header><div><h3>文档解析结果</h3><p>解析仅使用本地程序，不会产生模型调用或 Token 消耗。</p></div>
        <button type="button" className="secondary" disabled={!parsedMaterials.length}
          onClick={() => void downloadPageResult(projectId, "upload", "json").catch((reason) => setError(message(reason)))}>
          下载解析结果</button></header>
      {!parsedMaterials.length && <p className="empty-hint">尚未上传资料。</p>}
      {parsedMaterials.map((material) => <article className="material-result" key={material.asset_id}>
        <header><strong>{material.filename}</strong><span className={`status-pill ${material.parse_status}`}>
          {statusLabel(material.parse_status)}</span></header>
        <p>{material.format.toUpperCase()} · {formatBytes(material.size_bytes)} · {material.fragments.length} 个来源片段</p>
        {material.diagnostics.map((item) => <p key={`${item.code}-${item.message}`} className={item.severity === "error" ? "error" : "warning"}>
          {item.message}</p>)}
        {material.fragments.length > 0 && <RequirementMaterialStructure material={material} />}
      </article>)}
    </section>
  </section>;
}

export function PageHeader({ title, subtitle, badge }: { title: string; subtitle: string; badge?: string }) {
  return <header className="workflow-page-header"><div><p className="eyebrow">工作页</p><h2>{title}</h2><span>{subtitle}</span></div>
    {badge && <span className="page-badge">{badge}</span>}</header>;
}
const toBase64 = async (file: File): Promise<string> => {
  const bytes = new Uint8Array(await file.arrayBuffer()); let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); }); return btoa(binary);
};
const formatBytes = (value: number) => value < 1024 ? `${value} B` : `${(value / 1024).toFixed(1)} KiB`;
const statusLabel = (value: string) => ({ complete: "解析成功", partial: "部分解析", failed: "解析失败", rejected: "无法使用" })[value] ?? value;
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
