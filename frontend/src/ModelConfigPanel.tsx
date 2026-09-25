import { FormEvent, useEffect, useState } from "react";

import {
  clearSessionModelConfig, discoverSessionModels, getSessionModelConfig, listModelProviders, ModelOption,
  ModelProviderId, ModelProviderOption, saveSessionModelConfig, SessionModelConfig, testSessionModelConfig,
} from "./api";

const emptyConfig: SessionModelConfig = {
  provider: "siliconflow", model: "", base_url: "", api_key: "", remember_api_key: false,
};

export function ModelConfigPanel() {
  const [providers, setProviders] = useState<ModelProviderOption[]>([]);
  const [config, setConfig] = useState(emptyConfig);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        // 升级时只删除旧版本缓存的明文 Key，不读取或迁移其值。
        localStorage.removeItem("ai-test-design-model-config");
        const [options, saved] = await Promise.all([listModelProviders(), getSessionModelConfig()]);
        setProviders(options);
        if (saved) {
          setConfig({ provider: saved.provider, model: saved.model, base_url: saved.base_url, api_key: "", remember_api_key: false });
          setModels(saved.model_options);
          setMessage(statusMessage(saved.credential_source, saved.verification_status));
        } else selectProvider(options, "siliconflow", setConfig, setModels);
      } catch (reason) { setError(reason instanceof Error ? reason.message : "模型配置加载失败"); }
    };
    void load();
  }, []);

  const changeProvider = (provider: ModelProviderId) => selectProvider(providers, provider, setConfig, setModels);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const saved = await saveSessionModelConfig(config);
      setConfig({ ...config, api_key: "", remember_api_key: false });
      setModels(saved.model_options);
      setMessage(statusMessage(saved.credential_source, saved.verification_status));
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "模型配置保存失败"); }
  };
  const discover = async () => {
    setMessage("正在发现当前服务商可用模型…"); setError("");
    try {
      const result = await discoverSessionModels(config);
      if (result.success) {
        setModels(result.models);
        setMessage("已发现 " + result.models.length + " 个模型；页面刷新不会再次自动发现。");
      } else setError(formatModelError(result.error));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "模型发现失败"); }
  };
  const test = async () => {
    setMessage("正在执行连接测试…"); setError("");
    try {
      const result = await testSessionModelConfig(config);
      const refreshed = await getSessionModelConfig();
      if (refreshed) setModels(refreshed.model_options);
      if (result.success) setMessage(result.message ?? "模型连接测试成功");
      else setError(formatModelError(result.error));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "连接测试失败"); }
  };
  const clear = async () => {
    try {
      await clearSessionModelConfig();
      setConfig(emptyConfig); setModels([]);
      setMessage("已清除当前会话模型配置和临时 Key；已记住的本地 Key 未删除。"); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "清除模型配置失败"); }
  };

  return <section className="panel" aria-label="模型配置">
    <h2 id="model-config">模型配置</h2>
    <p>临时 API Key 仅保存在后端当前进程；只有勾选后才会写入被 Git 忽略的本地凭据文件，页面不会回显 Key。</p>
    <form className="project-form" onSubmit={submit}>
      <label>供应商<select value={config.provider} onChange={(event) => changeProvider(event.target.value as ModelProviderId)}>
        {providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <label>模型<input list="configured-model-options" value={config.model}
        onChange={(event) => setConfig({ ...config, model: event.target.value })} /></label>
      <datalist id="configured-model-options">
        {models.map((model) => <option key={model.id} value={model.id}>{stateLabel(model.state)}</option>)}
      </datalist>
      {models.length > 0 && <p className="muted">当前模型状态：{stateLabel(models.find((item) => item.id === config.model)?.state ?? "manual")}</p>}
      <label>Endpoint<input value={config.base_url}
        onChange={(event) => setConfig({ ...config, base_url: event.target.value })} /></label>
      <label>API Key<input type="password" autoComplete="off" value={config.api_key}
        onChange={(event) => setConfig({ ...config, api_key: event.target.value })} /></label>
      <label><input type="checkbox" checked={config.remember_api_key}
        onChange={(event) => setConfig({ ...config, remember_api_key: event.target.checked })} />记住此服务商的 API Key 到本地凭据文件</label>
      <div className="report-actions"><button type="submit">保存配置</button>
        <button type="button" onClick={() => void discover()}>发现模型</button>
        <button type="button" onClick={() => void test()}>连接测试</button>
        <button type="button" onClick={() => void clear()}>清除会话配置</button></div>
    </form>
    {message && <p role="status" className="success">{message}</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

function selectProvider(options: ModelProviderOption[], provider: ModelProviderId,
  setConfig: (config: SessionModelConfig) => void, setModels: (models: ModelOption[]) => void) {
  const option = options.find((item) => item.id === provider);
  const models = option?.models ?? [];
  setModels(models);
  setConfig({ provider, base_url: option?.base_url ?? "", model: models[0]?.id === "手动输入模型" ? "" : models[0]?.id ?? "",
    api_key: "", remember_api_key: false });
}

function formatModelError(error: { user_message: string; suggested_action: string; retryable: boolean } | null): string {
  if (!error) return "模型服务返回了未说明的失败";
  return error.user_message + "。建议：" + error.suggested_action + (error.retryable ? "（可重试）" : "");
}

function statusMessage(credentialSource: string, verificationStatus: string): string {
  const source = { temporary: "临时 Key", remembered_local: "本地已记住 Key", environment: "环境变量 Key", none: "未配置 Key" }[credentialSource] ?? credentialSource;
  return "凭据来源：" + source + "；连接状态：" + stateLabel(verificationStatus);
}

function stateLabel(state: string): string {
  return ({ preset: "预设", discovered: "已发现", verified: "已验证", failed: "失败", invalidated: "已失效", manual: "手动输入", unverified: "未验证" }[state] ?? state);
}
