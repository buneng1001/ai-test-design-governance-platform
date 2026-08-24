# Issue tracker：本地 Markdown

本项目的规格和实施任务保存在 `.scratch/` 下。即使后续配置 GitHub 远程仓库，除非本文件明确修改，否则
engineering skills 仍使用本地 Markdown，不发布 GitHub Issues。

## 约定

- 每项功能使用一个目录：`.scratch/<feature-slug>/`
- 功能规格保存为：`.scratch/<feature-slug>/spec.md`
- 实施任务保存为：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`
- 任务从 `01` 开始编号，每个任务单独一个文件，不生成合并任务文件。
- 每个任务文件顶部使用 `Status:` 记录 triage 状态。
- 评论和处理历史追加到文件底部的 `## Comments`。

## 发布规格或任务

当 skill 要求“发布到 issue tracker”时，在 `.scratch/<feature-slug>/` 下创建对应文件。

## 获取任务

读取用户提供的任务路径或编号对应的 Markdown 文件。

## Wayfinder 约定

- 路线图：`.scratch/<effort>/map.md`
- 子任务：`.scratch/<effort>/issues/NN-<slug>.md`
- `Type:` 使用 `research`、`prototype`、`grilling` 或 `task`
- `Status:` 使用 `claimed` 或 `resolved`
- `Blocked by:` 记录阻塞任务编号
- 领取任务前将状态改为 `claimed`
- 完成后追加 `## Answer`，将状态改为 `resolved`，并更新 `map.md`
