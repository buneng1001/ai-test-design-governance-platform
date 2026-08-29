import { FormEvent, useEffect, useState } from "react";

import {
  AssetProvenanceInput,
  AssetProvenanceRecord,
  createAsset,
  listAssets,
} from "./api";


const initialInput: AssetProvenanceInput = {
  name: "",
  asset_type: "requirement_material",
  provenance_kind: "original_synthetic",
  source: "",
  usage_permission: "project_owned",
  model_permission: "allowed",
  requirement_version: "V1",
  purpose: "",
  content_base64: "",
  change_reason: "首次登记",
};

export function AssetProvenancePanel({ projectId }: { projectId: number }) {
  const [assets, setAssets] = useState<AssetProvenanceRecord[]>([]);
  const [input, setInput] = useState(initialInput);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void listAssets(projectId).then(setAssets).catch((reason: unknown) => setError(message(reason)));
  }, [projectId]);

  const selectFiles = (files: FileList | null) => setSelectedFiles(Array.from(files ?? []));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (selectedFiles.length === 0 || !input.source || !input.purpose) {
      setError("请选择至少一个文件并填写来源、用途");
      return;
    }
    try {
      const created = await Promise.all(selectedFiles.map(async (file) => createAsset(projectId, {
        ...input, name: file.name, media_type: file.type || "application/octet-stream", content_base64: await toBase64(file),
      })));
      setAssets([...assets, ...created]);
      setInput(initialInput);
      setSelectedFiles([]);
      setError("");
    } catch (reason) {
      setError(message(reason));
    }
  };

  return (
    <section className="panel">
      <h2>资产来源记录</h2>
      <p>资产必须先登记来源、权限和内容哈希，来源不明资产不会进入需求资料包或模型上下文。</p>
      <form className="project-form" onSubmit={submit}>
        <label>资产文件<input type="file" multiple onChange={(event) => selectFiles(event.target.files)} /></label>
        {selectedFiles.length > 0 && <p>待登记：{selectedFiles.map((file) => file.name).join("、")}</p>}
        <label>资产类型<select value={input.asset_type} onChange={(event) => setInput({
          ...input,
          asset_type: event.target.value as AssetProvenanceInput["asset_type"],
        })}>
          <option value="requirement_material">需求资料</option>
          <option value="case_template">用例模板</option>
          <option value="mock_output">Mock 输出</option>
          <option value="evaluation_truth">评估真值</option>
          <option value="result_input">结果输入</option>
          <option value="other">其他</option>
        </select></label>
        <label>来源边界<select value={input.provenance_kind} onChange={(event) => setInput({
          ...input,
          provenance_kind: event.target.value as AssetProvenanceInput["provenance_kind"],
        })}>
          <option value="original_synthetic">原创合成</option>
          <option value="public_authorized">公开授权</option>
          <option value="prohibited">禁止使用</option>
        </select></label>
        <label>来源或创建方式<input value={input.source} onChange={(event) => setInput({
          ...input, source: event.target.value,
        })} /></label>
        <label>使用权限<select value={input.usage_permission} onChange={(event) => setInput({
          ...input,
          usage_permission: event.target.value as AssetProvenanceInput["usage_permission"],
        })}>
          <option value="project_owned">项目自有</option>
          <option value="public_license">公开许可</option>
          <option value="unknown">尚未确认</option>
          <option value="prohibited">禁止使用</option>
        </select></label>
        <label>模型使用权限<select value={input.model_permission} onChange={(event) => setInput({
          ...input,
          model_permission: event.target.value as AssetProvenanceInput["model_permission"],
        })}>
          <option value="allowed">允许</option>
          <option value="denied">不允许</option>
          <option value="unknown">尚未确认</option>
        </select></label>
        <label>需求版本<input value={input.requirement_version} onChange={(event) => setInput({
          ...input, requirement_version: event.target.value,
        })} /></label>
        <label>用途<input value={input.purpose} onChange={(event) => setInput({
          ...input, purpose: event.target.value,
        })} /></label>
        <button type="submit">登记资产来源</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="project-grid" aria-label="资产来源记录列表">
        {assets.map((asset) => <article className="project-card" key={asset.id}>
          <strong>{asset.name}</strong>
          <span>{boundaryLabel(asset.boundary)} · 修订 {asset.revision}</span>
          <span>大小：{asset.size_bytes} 字节</span>
          <span>{asset.reason}</span>
          <span>SHA-256：{asset.sha256}</span>
        </article>)}
      </div>
    </section>
  );
}

const boundaryLabel = (boundary: AssetProvenanceRecord["boundary"]): string => ({
  original_synthetic: "原创合成",
  public_authorized: "公开授权",
  prohibited: "禁止使用",
  unknown: "来源不明资产",
})[boundary];

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";

const toBase64 = async (file: File): Promise<string> => {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
};
