import type { TemplateMappingVersion } from "./api_types";
import type { GeneratedCase } from "./v020_types";

export function CaseTemplatePreview({ mapping, cases, onToggle, onEdit, onRemove }: {
  mapping: TemplateMappingVersion | null | undefined;
  cases: GeneratedCase[];
  onToggle: (item: GeneratedCase, included: boolean) => void;
  onEdit: (item: GeneratedCase) => void;
  onRemove: (item: GeneratedCase) => void;
}) {
  const sheet = mapping?.sheets.find((item) => item.role === "case" && item.participates);
  const columns = sheet?.columns ?? [];
  return <div className="data-table-wrap"><table aria-label="测试用例模板预览"><thead><tr>
    {columns.map((column) => <th key={column.index}>{column.name}</th>)}
  </tr></thead><tbody>{cases.map((item) => <tr key={item.id} className={item.removed ? "removed-row" : ""}>
    {columns.map((column, index) => {
      const field = sheet?.field_mapping[column.name] ?? "";
      return <td key={column.index}>{index === 0 && <input type="checkbox" aria-label={`纳入-${item.title}`}
        checked={item.included && !item.removed} disabled={item.removed}
        onChange={(event) => onToggle(item, event.target.checked)} />}{caseValue(item, field)}
        {field === "title" && <div className="table-actions"><button type="button" className="text-button" onClick={() => onEdit(item)}>编辑</button>
          <button type="button" className="text-button" onClick={() => onRemove(item)}>{item.removed ? "恢复" : "移除"}</button></div>}</td>;
    })}
  </tr>)}</tbody></table></div>;
}

function caseValue(item: GeneratedCase, field: string): string {
  const values: Record<string, string> = {
    external_case_number: item.external_case_number ?? item.id,
    title: item.title,
    priority: item.priority,
    preconditions: item.preconditions.join("；"),
    input: item.test_input,
    steps: item.steps.map((step) => `${step.order}. ${step.action}`).join("\n"),
    step_expectations: item.steps.map((step) => `${step.order}. ${step.expected}`).join("\n"),
    overall_expectation: item.overall_expectation,
    test_type: item.test_type ?? "",
    module: item.module ?? "",
    test_item: item.test_item ?? "",
    attachment: item.attachment ?? "",
    software_version: item.software_version ?? "",
  };
  return values[field] ?? "";
}
