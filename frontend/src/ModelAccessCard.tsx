import { useEffect, useState } from "react";

import { getSessionModelConfig, SessionModelConfigStatus } from "./api";
import { ModelConfigPanel } from "./ModelConfigPanel";

export function ModelAccessCard() {
  const [status, setStatus] = useState<SessionModelConfigStatus | null>(null);
  const [open, setOpen] = useState(false);
  const refresh = () => void getSessionModelConfig().then(setStatus).catch(() => setStatus(null));
  useEffect(refresh, []);
  return <section className="context-section" aria-label="当前模型配置">
    <h3>模型接入</h3>
    {status ? <><p>{status.provider} · {status.model}</p>
      <p>{credentialLabel(status.credential_source)} · {verificationLabel(status.verification_status)}</p></>
      : <p>尚未配置真实模型；本地模式仍可使用。</p>}
    <button type="button" className="secondary full-width" onClick={() => setOpen(true)}>打开已有模型配置</button>
    {open && <div className="modal-backdrop" role="presentation"><section className="modal-card" role="dialog" aria-modal="true" aria-label="已有模型配置">
      <header><div><p className="eyebrow">复用现有能力</p><h2>模型配置</h2></div>
        <button type="button" className="secondary" onClick={() => { setOpen(false); refresh(); }}>关闭</button></header>
      <ModelConfigPanel />
    </section></div>}
  </section>;
}

const credentialLabel = (value: string): string => ({ temporary: "临时 Key", remembered_local: "本地已记住 Key",
  environment: "环境变量 Key", none: "未配置 Key" })[value] ?? value;
const verificationLabel = (value: string): string => ({ verified: "已验证", unverified: "未验证", failed: "连接失败",
  invalidated: "验证已失效" })[value] ?? value;
