Status: pending

# API Key 持久化加密风险

## Risk

当前为支持关闭网页后继续使用，API Key 会持久化到本机 SQLite 和浏览器 `localStorage`，但尚未加密。
能够读取本机应用数据库或浏览器配置的人员可能获得 API Key。

## Follow-up

- 评估操作系统凭据管理能力，例如 Windows Credential Manager 或系统 Keychain。
- 为本地配置增加加密存储和密钥轮换策略。
- 部署到其他设备或多人环境前，完成用户身份隔离、加密存储和使用后清除能力。
- 在设置页面增加明确的清除入口和风险提示。

## Comments

- 2026-09-04：为满足关闭网页后恢复配置，本版本先实现本机持久化；加密存储列为后续风险，不作为当前修复的一部分。
