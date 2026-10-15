import { useMemo, useState } from "react";

import type { ModelOption } from "./api";

interface ModelPickerProps {
  disabled: boolean;
  models: ModelOption[];
  value: string;
  onChange: (value: string) => void;
}

export function ModelPicker({ disabled, models, value, onChange }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized ? models.filter((model) => model.id.toLocaleLowerCase().includes(normalized)) : models;
  }, [models, query]);

  return <div className="model-picker">
    <label htmlFor="model-value">模型</label>
    <div className="model-picker-value">
      <input id="model-value" disabled={disabled} value={value}
        onChange={(event) => onChange(event.target.value)} />
      <button type="button" disabled={disabled || models.length === 0}
        aria-expanded={open} aria-controls="configured-model-options"
        onClick={() => setOpen((current) => !current)}>
        {open ? "收起模型列表" : `选择模型（${models.length}）`}
      </button>
    </div>
    {open && <section className="model-options-panel" aria-label="模型选择列表">
      <label htmlFor="model-filter">筛选模型</label>
      <input id="model-filter" value={query} autoComplete="off"
        onChange={(event) => setQuery(event.target.value)} />
      <p className="muted">显示 {filtered.length} / {models.length} 个模型；列表随整个页面滚动。</p>
      <ul id="configured-model-options" className="model-option-list" role="listbox"
        aria-label="可用模型" data-scroll-container="page">
        {filtered.map((model) => <li key={model.id} role="option" aria-selected={model.id === value}>
          <button type="button" onClick={() => { onChange(model.id); setOpen(false); setQuery(""); }}>
            <span>{model.id}</span><small>{stateLabel(model.state)}</small>
          </button>
        </li>)}
      </ul>
      {filtered.length === 0 && <p className="muted">没有匹配的模型，可直接在上方模型输入框中手动填写。</p>}
    </section>}
  </div>;
}

function stateLabel(state: string): string {
  return ({ preset: "预设", discovered: "已发现", verified: "已验证", failed: "失败",
    invalidated: "已失效", manual: "手动输入", unverified: "未验证" }[state] ?? state);
}
