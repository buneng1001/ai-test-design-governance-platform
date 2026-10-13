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
  const [testing, setTesting] = useState(false);
  const [configurationDirty, setConfigurationDirty] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        // 升级时只删除旧版本缓存的明文 Key，不读取或迁移其值。
        localStorage.removeItem("ai-test-design-model-config");
        const [options, saved] = await Promise.all([listModelProviders(), getSessionModelConfig()]);
        setProviders(options);
        if (saved) {
          setConfig({ provider: saved.provider, model: "", base_url: saved.base_url, api_key: "", remember_api_key: false });
          setModels(saved.model_options);
          setConfigurationDirty(true);
          setMessage(`检测到上次保存配置：${saved.provider} / ${saved.model}；${statusMessage(saved.credential_source, saved.verification_status)}。为避免误用历史模型，本次未自动选择，请重新选择。`);
        } else selectProvider(options, "siliconflow", setConfig, setModels);
      } catch (reason) { setError(reason instanceof Error ? reason.message : "模型配置加载失败"); }
    };
    void load();
  }, []);

  const markConfigChanged = () => {
    setConfigurationDirty(true);
    setMessage("配置已修改，请重新测试连接。");
    setError("");
  };
  const invalidateCurrentResult = (nextConfig: SessionModelConfig) => {
    setConfig(nextConfig);
    markConfigChanged();
  };
  const changeProvider = (provider: ModelProviderId) => {
    selectProvider(providers, provider, setConfig, setModels);
    markConfigChanged();
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const saved = await saveSessionModelConfig(config);
      setConfig({ ...config, api_key: "", remember_api_key: false });
      setModels(saved.model_options);
      setConfigurationDirty(false);
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
        if (!result.models.some((model) => model.id === config.model)) {
          setConfig({ ...config, model: "" });
          setConfigurationDirty(true);
          setMessage("已刷新模型列表；上次选择的模型不在最新列表中，请重新选择。");
        } else setMessage("已发现 " + result.models.length + " 个模型；页面刷新不会再次自动发现。");
      } else setError(formatModelError(result.error));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "模型发现失败"); }
  };
  const test = async () => {
    const testedConfig = { ...config };
    setTesting(true); setMessage(`正在测试：${testedConfig.provider} / ${testedConfig.model}`); setError("");
    try {
      const result = await testSessionModelConfig(testedConfig);
      const refreshed = await getSessionModelConfig();
      if (refreshed) { setModels(refreshed.model_options); setConfigurationDirty(false); }
      if (result.success) setMessage(`${result.message ?? "模型连接测试成功"}：${result.provider} / ${result.model}`);
      else { setMessage(""); setError(formatModelError(result.error)); }
    } catch (reason) {
      setMessage(""); setError(reason instanceof Error ? reason.message : "连接测试失败");
    } finally { setTesting(false); }
  };
  const clear = async () => {
    try {
      await clearSessionModelConfig();
      setConfig(emptyConfig); setModels([]);
      setConfigurationDirty(true);
      setMessage("已清除当前会话模型配置和临时 Key；已记住的本地 Key 未删除。"); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "清除模型配置失败"); }
  };
  const configurationActionsDisabled = testing || !config.model.trim() || !config.base_url.trim();

  return <section className="panel" aria-label="模型配置">
    <h2 id="model-config">模型配置</h2>
    <p>临时 API Key 仅保存在后端当前进程；只有勾选后才会写入被 Git 忽略的本地凭据文件，页面不会回显 Key。</p>
    <form className="project-form" onSubmit={submit}>
      <label>供应商<select disabled={testing} value={config.provider}
        onChange={(event) => changeProvider(event.target.value as ModelProviderId)}>
        {providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <label>模型<input disabled={testing} list="configured-model-options" value={config.model}
        onChange={(event) => invalidateCurrentResult({ ...config, model: event.target.value })} /></label>
      <datalist id="configured-model-options">
        {models.map((model) => <option key={model.id} value={model.id}>{stateLabel(model.state)}</option>)}
      </datalist>
      {models.length > 0 && <p className="muted">当前模型状态：{configurationDirty
        ? "待重新测试" : stateLabel(models.find((item) => item.id === config.model)?.state ?? "manual")}</p>}
      <label>Endpoint<input disabled={testing} value={config.base_url}
        onChange={(event) => invalidateCurrentResult({ ...config, base_url: event.target.value })} /></label>
      <label>API Key<input disabled={testing} type="password" autoComplete="off" value={config.api_key}
        onChange={(event) => invalidateCurrentResult({ ...config, api_key: event.target.value })} /></label>
      <label><input disabled={testing} type="checkbox" checked={config.remember_api_key}
        onChange={(event) => setConfig({ ...config, remember_api_key: event.target.checked })} />记住此服务商的 API Key 到本地凭据文件</label>
      <div className="report-actions"><button type="submit" disabled={configurationActionsDisabled}>保存配置</button>
        <button type="button" disabled={configurationActionsDisabled}
          onClick={() => void discover()}>发现模型</button>
        <button type="button" disabled={configurationActionsDisabled}
          onClick={() => void test()}>{testing ? "正在测试…" : "连接测试"}</button>
        <button type="button" disabled={testing} onClick={() => void clear()}>清除会话配置</button></div>
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

function formatModelError(error: {
  user_message: string; suggested_action: string; retryable: boolean; error_type: string; detail: string | null;
} | null): string {
  if (!error) return "模型服务返回了未说明的失败";
  const diagnostics = [`错误类型：${error.error_type}`, error.detail, error.retryable ? "可重试" : "不可重试"];
  return `${error.user_message}。建议：${error.suggested_action}（${diagnostics.filter(Boolean).join("；")}）`;
}

function statusMessage(credentialSource: string, verificationStatus: string): string {
  const source = { temporary: "临时 Key", remembered_local: "本地已记住 Key", environment: "环境变量 Key", none: "未配置 Key" }[credentialSource] ?? credentialSource;
  return "凭据来源：" + source + "；连接状态：" + stateLabel(verificationStatus);
}

function stateLabel(state: string): string {
  return ({ preset: "预设", discovered: "已发现", verified: "已验证", failed: "失败", invalidated: "已失效", manual: "手动输入", unverified: "未验证" }[state] ?? state);
}
