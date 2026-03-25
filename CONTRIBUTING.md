# Contributing

简体中文在前，English summary 在后。

## 简体中文

感谢你为 `CJFCodexSwitcher` 做贡献。

### 你可以贡献什么

- Bug 修复
- 文档改进
- CLI / TUI 体验优化
- 安装与发布流程优化
- Agent / Skill 使用体验优化

### 提交 Issue 之前

请先确认：

1. 你使用的是最新 release 或最新 `main`
2. 你已经阅读 README 中的安装与使用说明
3. 同类问题没有在 Issues 中重复出现

### 提交 Pull Request 之前

请尽量保证：

1. 交互页面能正常运行
2. 非交互 CLI 至少验证以下命令中的相关项：
   - `codex-switcher --list`
   - `codex-switcher --list --json`
   - `codex-switcher --best --json`
   - `codex-switcher --switch ... --json`
3. 如果改动影响用户工作流，请同步更新：
   - `README.md`
   - `.codex/skills/codex-switcher-help/`

### 提交流程建议

1. Fork 仓库并创建分支
2. 完成修改
3. 自测
4. 提交 PR，描述：
   - 改了什么
   - 为什么要改
   - 如何验证

### 不建议提交的内容

- 本地账号快照
- usage 缓存
- 备份文件
- 运行时脚本
- 真实 token / refresh token / access token

这些内容已经被 `.gitignore` 排除，请不要强行提交。

## English

Thanks for contributing to `CJFCodexSwitcher`.

Please:

1. check the latest release or `main`
2. search for duplicate issues first
3. validate relevant interactive and non-interactive commands before opening a PR
4. update `README.md` and `.codex/skills/codex-switcher-help/` if your change affects user workflows
