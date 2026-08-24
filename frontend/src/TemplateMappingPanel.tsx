import { ChangeEvent, useState } from "react";

import { confirmTemplate, TemplateMappingVersion, TemplateSheet, uploadTemplate, validateTemplate } from "./api";

interface Props {
  projectId: number;
}

const roleLabels: Record<TemplateSheet["role"], string> = {
  case: "用例表", instruction: "说明表", dictionary: "字典表", statistics: "统计表", unknown: "未知",
};

export function TemplateMappingPanel({ projectId }: Props) {
  const [mapping, setMapping] = useState<TemplateMappingVersion | null>(null);
  const [error, setError] = useState("");

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const content = await readBase64(file);
      setMapping(await uploadTemplate(projectId, file.name, content));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "模板上传失败");
    }
  };

  const updateSheet = (index: number, update: Partial<TemplateSheet>) => {
    if (!mapping) return;
    setMapping({
      ...mapping,
      sheets: mapping.sheets.map((sheet, itemIndex) => itemIndex === index ? { ...sheet, ...update } : sheet),
    });
  };

  const confirm = async () => {
    if (!mapping) return;
    try {
      const validation = await validateTemplate(projectId, mapping.id, "测试工程师", mapping.sheets);
      if (!validation.valid) {
        setError(validation.diagnostics.map((item) => item.message).join("；"));
        return;
      }
      setMapping(await confirmTemplate(projectId, mapping.id, "测试工程师", mapping.sheets));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "模板映射确认失败");
    }
  };

  return <section className="panel" aria-label="用例模板映射">
    <h2>用例模板映射</h2>
    <label>上传 XLSX 或 CSV 用例模板<input type="file" accept=".xlsx,.csv" onChange={upload} /></label>
    {mapping && <div>
      <p>{mapping.filename}：发现 {mapping.sheets.length} 张工作表</p>
      {mapping.sheets.map((sheet, index) => <fieldset key={sheet.name}>
        <legend>{sheet.name}（AI 建议：{roleLabels[sheet.role_suggestion]}）</legend>
        <label>工作表角色<select value={sheet.role} onChange={(event) => updateSheet(index, {
          role: event.target.value as TemplateSheet["role"],
        })}>{Object.entries(roleLabels).map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}</select></label>
        <label><input type="checkbox" checked={sheet.participates} onChange={(event) => updateSheet(index, {
          participates: event.target.checked,
        })} />参与用例处理</label>
        <label>标题行<select value={sheet.title_row ?? ""} onChange={(event) => updateSheet(index, {
          title_row: Number(event.target.value),
        })}><option value="">请选择</option>{sheet.title_row_candidates.map((row) => (
          <option key={row} value={row}>第 {row} 行</option>
        ))}</select></label>
        <p>列：{sheet.columns.map((column) => column.name).join("、")}</p>
        <p>映射：{Object.entries(sheet.field_mapping).map(([column, field]) => `${column}→${field}`).join("，") || "无"}</p>
      </fieldset>)}
      <button onClick={() => void confirm()} disabled={mapping.status === "confirmed"}>确认模板映射</button>
      {mapping.status === "confirmed" && <p role="status">模板映射已确认，版本 {mapping.version}。</p>}
    </div>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

const readBase64 = (file: File): Promise<string> => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
  reader.onerror = () => reject(reader.error ?? new Error("模板文件读取失败"));
  reader.readAsDataURL(file);
});
