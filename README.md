# CJFCodexSwitcher

多个 Codex 账号快速切换与余量查看工具

[![Release](https://img.shields.io/github/v/release/mileson/CJFCodexSwitcher?display_name=tag)](https://github.com/mileson/CJFCodexSwitcher/releases)
[![License](https://img.shields.io/github/license/mileson/CJFCodexSwitcher)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![Homebrew](https://img.shields.io/badge/Homebrew-installable-FBB040?logo=homebrew&logoColor=black)](https://github.com/mileson/homebrew-cjfcodexswitcher)
[![GitHub Stars](https://img.shields.io/github/stars/mileson/CJFCodexSwitcher?style=social)](https://github.com/mileson/CJFCodexSwitcher/stargazers)
[![Last Commit](https://img.shields.io/github/last-commit/mileson/CJFCodexSwitcher)](https://github.com/mileson/CJFCodexSwitcher/commits/main)
[![Downloads](https://img.shields.io/github/downloads/mileson/CJFCodexSwitcher/total)](https://github.com/mileson/CJFCodexSwitcher/releases)

![CJFCodexSwitcher Screenshot](docs/images/overview.png)

**语言切换 / Language**

[简体中文](#简体中文) | [English](#english)

---

## 简体中文

`CJFCodexSwitcher` 是一个面向多账号使用场景的 Codex 账号管理工具，适合两类人：

- 新手用户：直接打开工具，看所有账号余量并快速切换
- Agent / 自动化脚本：通过非交互 CLI 命令拿到排序后的账号列表、最佳账号和切换结果

### 功能亮点

- 实时查看所有账号的 5 小时 / 每周余量与下次重置时间
- 启动后直接进入账号列表页面，无需先进入主菜单
- 当前账号用 `[当前]` 标记，并支持直接按序号切换
- 切换成功后自动刷新页面
- 多个账号并发实时刷新，减少等待时间
- 提供 Agent 友好的非交互 CLI：`--list`、`--json`、`--best`、`--switch`、`--save-current`
- 项目内置专用 Skill，方便 Agent 按统一规则操作

### 技术栈

| 层级 | 技术 |
|------|------|
| Runtime | Python 3 |
| Network | Python 标准库 `urllib` |
| Packaging | `pyproject.toml` + `setuptools` |
| UI | Terminal TUI |

### 一句话安装

```bash
brew tap mileson/cjfcodexswitcher && brew install cjfcodexswitcher
```

```bash
pipx install git+https://github.com/mileson/CJFCodexSwitcher.git
```

### 新手安装教程

前置要求：

- Python 3.8+
- 本机已经使用过 Codex，并存在 `~/.codex/auth.json`

从源码安装：

```bash
git clone https://github.com/mileson/CJFCodexSwitcher.git
cd CJFCodexSwitcher
python3 install.py
source ~/.zshrc  # 或 ~/.bashrc
codex-switcher
```

如果不用 `pipx`，也可以直接安装：

```bash
python3 -m pip install "git+https://github.com/mileson/CJFCodexSwitcher.git"
```

### 使用说明

工具启动后会直接进入“查看所有账号余量”页面，并显示统一账号列表。

页面中的核心字段：

- `邮箱`：账号邮箱
- `PLAN`：计划类型，例如 `TEAM`
- `5小时`：当前 5 小时额度剩余百分比和下次重置时间
- `每周`：当前每周额度剩余百分比和下次重置时间
- `[当前]`：当前正在使用的账号

底部操作：

- `Enter`：刷新当前页面
- 输入 `#` 序号：切换到对应账号
- 输入 `S`：存档当前账号（仅当前账号未存档时显示）
- 输入 `0`：退出工具

### Agent / CLI 快捷命令

```bash
# 实时列出账号，按 5 小时余量、1 周余量排序
codex-switcher --list

# 以 JSON 输出账号列表
codex-switcher --list --json

# 输出当前最佳账号
codex-switcher --best
codex-switcher --best --json

# 按排序序号、邮箱或 best 切换账号
codex-switcher --switch 2
codex-switcher --switch user@example.com
codex-switcher --switch best

# 切换结果用 JSON 返回
codex-switcher --switch best --json

# 非交互存档当前账号
codex-switcher --save-current
codex-switcher --save-current my-account

# 刷新当前账号 usage
codex-switcher --refresh
```

排序规则：

1. 先按 5 小时剩余量降序
2. 相同则按 1 周剩余量降序
3. 最后按邮箱升序作为 tie-breaker

### 给 Agent 的可复制提示词

```text
请帮我安装并配置 CJFCodexSwitcher，然后使用项目内 Skill `/Users/mileson/codex-switcher/.codex/skills/codex-switcher-help/SKILL.md` 作为操作规范。优先使用非交互 CLI，不要手动驱动 TUI。步骤要求：
1. 安装或校验 `codex-switcher` 命令可用
2. 运行 `codex-switcher --list --json` 检查账号列表
3. 运行 `codex-switcher --best --json` 判断当前最佳账号
4. 如有需要，运行 `codex-switcher --switch best --json`
5. 最后请你自己验证命令执行通过，并反馈：
   - 验证是否成功
   - 当前最佳账号是谁
   - 如果发生切换，切换到了哪个账号
   - 后续我还可以如何使用这个工具
```

### 项目结构

```text
CJFCodexSwitcher/
├── codex_switcher.py                  # 主实现模块
├── codex-switcher.py                  # 命令入口包装器
├── install.py                         # 本地安装脚本
├── pyproject.toml                     # Python 打包与 console script 入口
├── README.md                          # 双语文档
├── .codex/skills/codex-switcher-help/ # 项目内 Skill
└── docs/                              # 截图与 release notes
```

### 安全说明

- 本仓库不会提交本地账号快照、usage 缓存、备份文件或运行时脚本
- 真实账号数据只保存在本机本地目录，例如 `accounts/`、`usage_cache/`、`backups/`
- 如果你 fork 或二次发布本仓库，请保持这些目录继续被 `.gitignore` 排除

### 贡献方式

欢迎提交 Issue 或 PR。建议在提交前至少确认：

1. 交互页面行为正常
2. 非交互 CLI 的文本输出和 JSON 输出都可用
3. 如果改动影响工作流，项目内 Skill 和 README 也同步更新

### Release

当前推荐版本 release notes：

- [v0.1.1 Release Notes](docs/releases/v0.1.1.md)

### License

MIT

---

## English

`CJFCodexSwitcher` is a fast multi-account Codex switcher and quota viewer for two audiences:

- end users who want a simple interactive account list
- agents or scripts that need stable non-interactive CLI commands

### Highlights

- live 5-hour and weekly quota view for multiple accounts
- direct startup into the account list page
- `[当前]` marker for the active account
- automatic refresh after switching
- concurrent live refresh for multiple accounts
- agent-friendly CLI: `--list`, `--json`, `--best`, `--switch`, `--save-current`
- repository-local skill for guided agent usage

### One-Line Install

```bash
brew tap mileson/cjfcodexswitcher && brew install cjfcodexswitcher
```

```bash
pipx install git+https://github.com/mileson/CJFCodexSwitcher.git
```

### Quick Start

```bash
git clone https://github.com/mileson/CJFCodexSwitcher.git
cd CJFCodexSwitcher
python3 install.py
source ~/.zshrc  # or ~/.bashrc
codex-switcher
```

### CLI Commands

```bash
codex-switcher --list
codex-switcher --list --json
codex-switcher --best --json
codex-switcher --switch best --json
codex-switcher --save-current
codex-switcher --refresh
```

### Agent Prompt

Use the repository-local skill:

```text
/Users/mileson/codex-switcher/.codex/skills/codex-switcher-help/SKILL.md
```

Then prefer non-interactive commands such as `--list --json`, `--best --json`, and `--switch best --json`.

### License

MIT
