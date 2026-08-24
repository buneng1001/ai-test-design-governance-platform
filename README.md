# AI 测试设计与治理平台

供单个本地测试工程师使用的测试设计与治理平台。当前任务 01 只提供测试设计项目创建、查看和编辑闭环，
不包含登录、多人权限、设备或浏览器控制，也不执行测试任务。

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

浏览器访问 `http://127.0.0.1:5173`。SQLite 数据默认保存在 `data/app.db`；可通过后端环境变量
`APP_DATABASE_PATH` 指定其他路径。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pytest
pnpm test
pnpm build
```

这些基础检查只使用本地 SQLite 和前端 Mock 请求，不调用模型或其他外部服务。

