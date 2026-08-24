import { ChangeEvent, FormEvent, useEffect, useState } from "react";

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
  const [name, setName] = useState("");
  const [files, setFiles] = useState<RequirementFileInput[]>([]);
  const [draft, setDraft] = useState<RequirementPackage | null>(null);
  const [versions, setVersions] = useState<RequirementVersion[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void listRequirementVersions(projectId).then(setVersions).catch((reason: unknown) => setError(message(reason)));
  }, [projectId]);

  const selectFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    if (selected.length === 0) return;
    try {
      const assets = await listAssets(projectId);
      const inputs = await Promise.all(selected.map(async (file) => {
        const asset = assets.find((candidate) => candidate.name === file.name);
        if (!asset) throw new Error(`${file.name} 尚未登记资产来源`);
        return {
          asset_id: asset.id,
          filename: file.name,
          media_type: file.type || "application/octet-stream",
          content_base64: await toBase64(file),
        };
      }));
      setFiles(inputs);
      setError("");
    } catch (reason) {
      setFiles([]);
      setError(message(reason));
    }
  };

  const inspect = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || files.length === 0) {
      setError("请填写资料包名称并选择已登记来源的需求资料");
      return;
    }
    try {
      setDraft(await createRequirementPackage(projectId, name, files));
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
        <label>需求资料包名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>需求资料文件<input type="file" multiple accept=".md,.txt,.json,.yaml,.yml" onChange={selectFiles} /></label>
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
          {material.diagnostics.map((diagnostic) => <p className="error" key={diagnostic.code}>
            {diagnostic.message}
          </p>)}
        </article>)}
        <button disabled={draft.status === "published"} onClick={() => void publish()}>
          {draft.status === "published" ? "已发布需求版本" : "发布需求版本"}
        </button>
      </div>}
      <div className="version-list" aria-label="需求版本列表">
        {versions.map((version) => <span key={version.id}>V{version.version} · {version.name}</span>)}
      </div>
    </section>
  );
}

const toBase64 = async (file: File): Promise<string> => {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
};

const statusLabel = (status: RequirementPackage["materials"][number]["parse_status"]): string => ({
  complete: "解析完整",
  partial: "部分解析",
  failed: "解析失败",
  rejected: "已拒绝",
})[status];

const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
