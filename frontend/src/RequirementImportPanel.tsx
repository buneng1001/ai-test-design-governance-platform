import { ChangeEvent, useEffect, useMemo, useState } from "react";

import {
  createAsset,
  createRequirementPackage,
  listRequirementVersions,
  publishRequirementPackage,
  reparseRequirementPackage,
  RequirementPackage,
  RequirementVersion,
} from "./api";
import { RequirementMaterialStructure } from "./RequirementMaterialStructure";

type RequirementImportPanelProps = {
  projectId: number;
  testObject: string;
  softwareVersion: string;
  onVersionPublished?: (versionId: number) => void;
};

type UploadProblem = { filename: string; message: string };

const supportedFormats = ".md,.txt,.json,.yaml,.yml,.docx,.pdf,.png,.jpg,.jpeg";

export function RequirementImportPanel({
  projectId,
  testObject,
  softwareVersion,
  onVersionPublished,
}: RequirementImportPanelProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [source, setSource] = useState("用户上传");
  const [draft, setDraft] = useState<RequirementPackage | null>(null);
  const [versions, setVersions] = useState<RequirementVersion[]>([]);
  const [uploadProblems, setUploadProblems] = useState<UploadProblem[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const successfulMaterials = useMemo(
    () => draft?.materials.filter((material) => material.parse_status === "complete" || material.parse_status === "partial") ?? [],
    [draft],
  );
  const failedMaterials = useMemo(
    () => draft?.materials.filter((material) => material.parse_status === "failed" || material.parse_status === "rejected") ?? [],
    [draft],
  );

  useEffect(() => {
    void listRequirementVersions(projectId).then(setVersions).catch((reason: unknown) => setError(message(reason)));
  }, [projectId]);

  const selectFiles = (event: ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(Array.from(event.target.files ?? []));
    setUploadProblems([]);
    setError("");
  };

  const uploadAndParse = async () => {
    if (selectedFiles.length === 0) {
      setError("请选择至少一份需求资料后再解析");
      return;
    }
    setBusy(true);
    setError("");
    const files = [];
    const problems: UploadProblem[] = [];
    for (const file of selectedFiles) {
      try {
        const asset = await createAsset(projectId, {
          name: file.name,
          media_type: file.type || "application/octet-stream",
          asset_type: "requirement_material",
          provenance_kind: "original_synthetic",
          source: source.trim() || "用户上传",
          usage_permission: "project_owned",
          model_permission: "allowed",
          requirement_version: "当前材料基线",
          purpose: "Step 00 需求材料解析",
          content_base64: await toBase64(file),
          change_reason: "上传并建立 Step 00 材料基线",
        });
        files.push({ asset_id: asset.id, filename: asset.name, media_type: asset.media_type, content_base64: "" });
      } catch (reason) {
        problems.push({ filename: file.name, message: message(reason) });
      }
    }
    setUploadProblems(problems);
    try {
      if (files.length === 0) {
        setError("没有文件完成来源登记，请根据下方诊断修复后重试");
        return;
      }
      setDraft(await createRequirementPackage(projectId, "当前任务材料基线", files));
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const reparse = async (assetIds: number[]) => {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      setDraft(await reparseRequirementPackage(projectId, draft.id, assetIds));
      setUploadProblems([]);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const version = await publishRequirementPackage(projectId, draft.id);
      setVersions((current) => [...current, version]);
      setDraft((current) => current ? { ...current, status: "published", published_version_id: version.id } : current);
      onVersionPublished?.(version.id);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="requirement-upload" aria-label="上传文档与 Step 00 解析">
      <h3>上传需求资料</h3>
      <p>支持 Markdown、文本、JSON、YAML、OpenAPI、DOCX、PDF 和 PNG/JPG 图片；每个文件会保留来源资产与内容定位。</p>
      <label className="upload-file-field">
        需求文件
        <input aria-label="需求文件" type="file" multiple accept={supportedFormats} onChange={selectFiles} />
      </label>
      <label className="upload-source-field">
        文件来源或创建方式
        <input aria-label="文件来源或创建方式" value={source} maxLength={2000}
          onChange={(event) => setSource(event.target.value)} />
      </label>
      {selectedFiles.length > 0 && <ul className="upload-file-list" aria-label="待解析文件">
        {selectedFiles.map((file) => <li key={`${file.name}-${file.size}`}>
          {file.name} · {formatForName(file.name)} · {formatBytes(file.size)}
        </li>)}
      </ul>}
      <button type="button" onClick={() => void uploadAndParse()} disabled={busy}>
        {busy ? "正在上传并解析…" : "上传并解析"}
      </button>
      {error && <p role="alert" className="error">{error}</p>}
      {uploadProblems.map((problem) => <p role="alert" className="error" key={problem.filename}>
        {problem.filename}：登记失败，{problem.message}
      </p>)}

      {draft && <section className="step00-baseline" aria-label="Step 00 材料基线">
        <h3>Step 00 材料基线</h3>
        <p>测试对象：{testObject}；软件版本：{softwareVersion}</p>
        <p>材料版本：{draft.status === "published" ? `V${versions.find((version) => version.id === draft.published_version_id)?.version ?? "已发布"}` : "草稿，尚未发布"}</p>
        <p>{successfulMaterials.length} 份可继续使用，{failedMaterials.length + uploadProblems.length} 份需要处理。</p>
        {draft.materials.map((material) => <article className="requirement-material" key={material.asset_id}>
          <strong>{material.filename}</strong>
          <span>{formatLabel(material.format)} · {formatBytes(material.size_bytes || base64Size(material.content_base64))} · {statusLabel(material.parse_status)}</span>
          {material.diagnostics.map((diagnostic) => <p className={diagnostic.severity === "error" ? "error" : "warning"}
            key={`${diagnostic.code}-${diagnostic.message}`}>{diagnostic.message}</p>)}
          {material.fragments.length > 0 && <RequirementMaterialStructure material={material} />}
          {material.visual_inferences.map((candidate) => <p key={candidate.source_reference.reference_id}>
            图片线索（待人工确认）：{candidate.description}；来源位置：{candidate.source_reference.locator}
          </p>)}
        </article>)}
        {failedMaterials.length > 0 && draft.status === "draft" && <button type="button" disabled={busy}
          onClick={() => void reparse(failedMaterials.map((material) => material.asset_id))}>只重试失败项</button>}
        {draft.status === "draft" && <button type="button" disabled={busy}
          onClick={() => void reparse(draft.materials.map((material) => material.asset_id))}>重新建立当前材料版本</button>}
        {successfulMaterials.length > 0 && draft.status === "draft" && <button type="button" disabled={busy}
          onClick={() => void publish()}>发布 Step 00 材料基线</button>}
        {successfulMaterials.length === 0 && <p className="error">全部文件均未成功解析。请检查格式、文件是否损坏；扫描版 PDF 请先 OCR 或提供可复制文本，然后重新上传或重试失败项。</p>}
      </section>}
      {versions.length > 0 && <section className="version-list" aria-label="已发布 Step 00 材料版本">
        <h3>已发布材料版本</h3>
        {versions.map((version) => <article key={version.id}>
          <strong>V{version.version} · {version.name}</strong>
          <span>{version.materials.map((material) => `${material.filename}：${statusLabel(material.parse_status)}`).join("；")}</span>
        </article>)}
      </section>}
    </section>
  );
}

const statusLabel = (status: RequirementPackage["materials"][number]["parse_status"]): string => ({
  complete: "解析完整", partial: "部分解析", failed: "解析失败", rejected: "已拒绝",
})[status];

const formatLabel = (format: RequirementPackage["materials"][number]["format"]): string => ({
  markdown: "Markdown", text: "文本", json: "JSON", yaml: "YAML", openapi: "OpenAPI", docx: "DOCX",
  pdf: "PDF", png: "PNG 图片", jpg: "JPG 图片", unsupported: "不支持的格式",
})[format];

const formatForName = (name: string): string => formatLabel(({
  md: "markdown", txt: "text", json: "json", yaml: "yaml", yml: "yaml", docx: "docx", pdf: "pdf",
  png: "png", jpg: "jpg", jpeg: "jpg",
}[name.split(".").pop()?.toLowerCase() ?? ""] ?? "unsupported") as RequirementPackage["materials"][number]["format"]);

const formatBytes = (size: number): string => size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KiB`;

const base64Size = (content: string): number => Math.max(0, Math.floor(content.length * 3 / 4) - (content.endsWith("==") ? 2 : content.endsWith("=") ? 1 : 0));

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";

const toBase64 = async (file: File): Promise<string> => {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
};
