# 02 — 真实模型配置与安全隔离

**What to build:** 增加会话级 API Key 配置、预置供应商与模型下拉选择、连接测试、真实模型适配和 Mock/真实结果区分。

**Blocked by:** 01 — 项目软件版本与保存反馈。

**Status:** pending

- 支持供应商、模型、Base URL、API Key、连接测试和清除。
- 预置 DeepSeek、硅基流动、Kimi、GLM 及其模型下拉列表。
- 自定义模式允许用户手填 Base URL 和模型名称。
- API Key 不进入持久化、日志、响应、报告或导出物。
- 真实模型失败不得伪装为 Mock 或成功结果。
- 真实和 Mock AI 运行在页面与审计记录中明确区分。
