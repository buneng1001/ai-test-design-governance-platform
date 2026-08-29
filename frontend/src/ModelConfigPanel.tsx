import { FormEvent, useEffect, useState } from "react";
import {
  clearSessionModelConfig, getSessionModelConfig, listModelProviders, ModelProviderId,
  ModelProviderOption, readStoredSessionModelConfig, saveSessionModelConfig, SessionModelConfig, testSessionModelConfig,
} from "./api";

const emptyConfig: SessionModelConfig = {
  provider: "siliconflow", model: "", base_url: "", api_key: "",
};

export function ModelConfigPanel() {
  const [providers, setProviders] = useState<ModelProviderOption[]>([]);
  const [config, setConfig] = useState(emptyConfig);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [options, saved] = await Promise.all([listModelProviders(), getSessionModelConfig()]);
        setProviders(options);
        if (saved) setConfig(readStoredSessionModelConfig() ?? { ...saved, api_key: "" });
        else selectProvider(options, "siliconflow", setConfig, config);
      } catch (reason) { setError(reason instanceof Error ? reason.message : "模型配置加载失败"); }
    };
    void load();
  }, []);

  const changeProvider = (provider: ModelProviderId) => selectProvider(providers, provider, setConfig, config);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await saveSessionModelConfig(config);
      setMessage("配置已保存到当前浏览器会话，API Key 不会写入服务器存储");
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "模型配置保存失败"); }
  };
  const test = async () => {
    try {
      const result = await testSessionModelConfig(config);
      setMessage(result.message);
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "连接测试失败"); }
  };
  const clear = async () => {
    try {
      await clearSessionModelConfig(); setConfig(emptyConfig); setMessage("已清除当前会话模型配置"); setError("");
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "清除配置失败"); }
  };

  const selectedProvider = providers.find((item) => item.id === config.provider);
  return <section className="panel" aria-label="模型配置">
    <h2>模型配置</h2>
    <p>真实模型配置只在当前浏览器会话使用；Mock AI 仍可离线使用，并会明确标记。</p>
    <form className="project-form" onSubmit={submit}>
      <label>供应商<select value={config.provider}
        onChange={(event) => changeProvider(event.target.value as ModelProviderId)}>
        {providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <label>模型{config.provider === "custom" ? <input value={config.model}
        onChange={(event) => setConfig({ ...config, model: event.target.value })} />
        : <select value={config.model} onChange={(event) => setConfig({ ...config, model: event.target.value })}>
          {selectedProvider?.models.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>}</label>
      <label>Base URL<input value={config.base_url}
        onChange={(event) => setConfig({ ...config, base_url: event.target.value })} /></label>
      <label>API Key<input type="password" autoComplete="off" value={config.api_key}
        onChange={(event) => setConfig({ ...config, api_key: event.target.value })} /></label>
      <div className="report-actions"><button type="submit">保存配置</button>
        <button type="button" onClick={() => void test()}>连接测试</button>
        <button type="button" onClick={() => void clear()}>清除配置</button></div>
    </form>
    {message && <p role="status" className="success">{message}</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

function selectProvider(options: ModelProviderOption[], provider: ModelProviderId,
  setConfig: (config: SessionModelConfig) => void, current: SessionModelConfig) {
  const option = options.find((item) => item.id === provider);
  setConfig({ ...current, provider, base_url: option?.base_url ?? "", model: option?.models[0] ?? "" });
}
