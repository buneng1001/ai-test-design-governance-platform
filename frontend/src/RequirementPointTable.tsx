import type { ReactNode } from "react";

export interface RequirementPointView {
  id: string;
  total_index?: number;
  module: string;
  test_item: string;
  test_basis: string;
  test_source: string;
  test_type: string;
  priority: string;
  related_requirement_id: string;
  selected?: boolean;
  action?: ReactNode;
}

export const requirementPointHeaders = [
  "总序号", "模块", "测试项", "测试项依据", "测试项来源", "测试类型", "优先级", "关联需求ID",
];

export function RequirementPointTable({ rows, selectable = false, onSelectionChange }: {
  rows: RequirementPointView[];
  selectable?: boolean;
  onSelectionChange?: (id: string, selected: boolean) => void;
}) {
  return <div className="data-table-wrap"><table aria-label="需求点分析表"><thead><tr>
    {selectable && <th>纳入范围</th>}
    {requirementPointHeaders.map((header) => <th key={header}>{header}</th>)}
  </tr></thead><tbody>{rows.map((row, index) => <tr key={row.id}>
    {selectable && <td><input aria-label={`选择-${row.test_item}`} type="checkbox" checked={Boolean(row.selected)}
      onChange={(event) => onSelectionChange?.(row.id, event.target.checked)} /></td>}
    <td>{row.total_index ?? index + 1}</td><td>{row.module}</td><td>{row.test_item}{row.action}</td>
    <td>{row.test_basis}</td><td>{row.test_source}</td><td>{row.test_type}</td><td>{row.priority}</td>
    <td>{row.related_requirement_id}</td>
  </tr>)}</tbody></table></div>;
}
