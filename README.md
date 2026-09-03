# AI 测试设计与治理平台

当前发布标识：`v0.1.0-rc.2`。

供单个本地测试工程师使用的测试设计与治理平台。当前已提供测试设计项目闭环，以及资产来源记录、SHA-256 校验、
不可覆盖的来源修订历史和需求资料包/模型上下文准入护栏。测试工程师可导入 Markdown、TXT、JSON、YAML 和
OpenAPI 资料，先查看逐文件解析结果与诊断，再发布不可覆盖的需求版本。不包含登录、多人权限、设备或浏览器控制，
也不执行测试任务。

项目工作台可登记原创合成、公开授权或禁止使用的资产。普通资产不会保存登记时提交的内容，只保存确定性计算的
SHA-256 与来源记录；评估真值只允许后端隔离保存，不能进入普通模型上下文、API 响应、报告或导出物。来源或权限不明确的
资产会被标记为来源不明资产并阻止进入后续流程。

需求资料导入会再次核对最新资产来源记录与 SHA-256。首版支持 Markdown、TXT、JSON、YAML、OpenAPI、DOCX、可提取文本的
PDF、PNG 和 JPG。单文件上限为 2 MiB；不支持、不可读、格式错误、哈希不一致或只能部分解析的文件会显示明确诊断。
扫描版 PDF 不承诺完整 OCR；图片只生成带原始资产引用的视觉推断候选，必须人工确认后才能成为需求事实。发布时只要资料包含有完整或部分解析结果即可形成新需求版本，历史版本不会被覆盖。

## 环境

- Python 3.12+
- Node.js 24+
- pnpm 11

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
pnpm install --frozen-lockfile
```

## 本地启动

分别在两个终端运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
pnpm dev
```

浏览器访问 `http://127.0.0.1:5174`。SQLite 数据默认保存在 `data/app.db`；可通过后端环境变量
`APP_DATABASE_PATH` 指定其他路径。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pytest
pnpm test
pnpm build
```

这些基础检查只使用本地 SQLite 和前端 Mock 请求，不调用模型或其他外部服务。

## rc.2 验收

第 5 阶段的 Mock 全闭环验收覆盖多文件需求分析、冲突处理、需求确认、用例编辑/移除/恢复和 16 列导出：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_rc2_acceptance.py
```

真实模型验收默认跳过。设置 `RC2_REAL_MODEL_BASE_URL`、`RC2_REAL_MODEL_API_KEY` 和
`RC2_REAL_MODEL_NAME` 后，会额外验证真实模型标识及 API Key 不进入审计导出；密钥只通过当前进程环境变量提供。

## 许可证

本项目采用 [MIT License](LICENSE)。
