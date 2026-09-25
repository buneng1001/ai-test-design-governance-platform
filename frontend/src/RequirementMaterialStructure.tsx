import { RequirementMaterial } from "./api";

export function RequirementMaterialStructure({ material }: { material: RequirementMaterial }) {
  const headings = material.fragments.filter((fragment) => fragment.kind === "heading" || /^#{1,6}\s+/.test(fragment.text));
  const tableCells = material.fragments.filter((fragment) => fragment.kind === "table_cell" || fragment.source_reference.locator.startsWith("table:"));
  const title = headings[0]?.text.replace(/^#+\s*/, "").trim();

  return <details>
    <summary>查看文档结构、章节/表格与来源位置</summary>
    <p>文档标题：{title || `未从正文识别标题（文件名：${material.filename}）`}</p>
    <h4>章节</h4>
    {headings.length > 0 ? <ul>
      {headings.map((fragment) => <li key={fragment.source_reference.reference_id}>
        <code>{fragment.source_reference.locator}</code>：{fragment.text.replace(/^#+\s*/, "")}
      </li>)}
    </ul> : <p>未识别可结构化章节；可在下方按来源位置查看正文。</p>}
    <h4>表格</h4>
    {tableCells.length > 0 ? <ul>
      {tableCells.map((fragment) => <li key={fragment.source_reference.reference_id}>
        <code>{fragment.source_reference.locator}</code>：{fragment.text}
      </li>)}
    </ul> : <p>未解析到表格单元格。</p>}
    <h4>全部内容与来源位置</h4>
    <ul>
      {material.fragments.map((fragment) => <li key={fragment.source_reference.reference_id}>
        <code>{fragment.source_reference.locator}</code>：{fragment.text}
      </li>)}
    </ul>
  </details>;
}
