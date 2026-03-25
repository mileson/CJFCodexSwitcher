# CJFCodexSwitcher

跨平台 Codex 账号切换与余量查看工具，面向两类用户：

- 新手用户：打开后直接进入账号列表页面，查看 5 小时 / 每周余量并快速切换账号
- Agent / 自动化脚本：通过非交互 CLI 参数获取排序后的账号列表、最佳账号和切换结果

[![Release](https://img.shields.io/github/v/release/mileson/CJFCodexSwitcher?display_name=tag)](https://github.com/mileson/CJFCodexSwitcher/releases)
[![License](https://img.shields.io/github/license/mileson/CJFCodexSwitcher)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![Homebrew](https://img.shields.io/badge/Homebrew-installable-FBB040?logo=homebrew&logoColor=black)](https://github.com/mileson/homebrew-cjfcodexswitcher)

![CJFCodexSwitcher Screenshot](docs/images/overview.png)

## Features

- 实时查看所有账号的 5 小时与每周余量、下次重置时间
- 按 `[当前]` 标记当前激活账号，并支持直接按序号切换
- 切换成功后自动刷新页面，并支持重启 Codex 客户端
- 并发实时刷新多个账号，降低等待时间
- 支持 Agent 友好的 CLI：`--list`、`--json`、`--best`、`--switch`、`--save-current`
- 项目内置专用 Skill，指导 Agent 和用户使用本工具

## Tech Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3 |
| Network | Python stdlib `urllib` |
| Packaging | `pyproject.toml` + `setuptools` |
| UI | Terminal TUI |

## Quick Start

### 一句话安装

```bash
brew tap mileson/cjfcodexswitcher && brew install cjfcodexswitcher
```

```bash
pipx install git+https://github.com/mileson/CJFCodexSwitcher.git
```

### Prerequisites

- Python 3.8+
- 已在本机使用过 Codex，并存在 `~/.codex/auth.json`

### 新手安装

```bash
git clone https://github.com/mileson/CJFCodexSwitcher.git
cd CJFCodexSwitcher
python3 install.py
source ~/.zshrc  # 或 ~/.bashrc
codex-switcher
```

### 更快的全局安装

如果你更习惯标准 Python 工具链，推荐使用：

```bash
pipx install git+https://github.com/mileson/CJFCodexSwitcher.git
```

如果你不用 `pipx`，也可以直接运行：

```bash
python3 -m pip install "git+https://github.com/mileson/CJFCodexSwitcher.git"
```

安装完成后直接运行：

```bash
codex-switcher
csw
```

## Beginner Tutorial

首次启动后，工具会直接进入“查看所有账号余量”页面：

```text
════════════════════════════════════════════════════════════
  Codex Switcher - 账号管理工具
════════════════════════════════════════════════════════════

>>> 查看所有账号余量
```

页面中的核心信息：

- `邮箱`：账号邮箱
- `PLAN`：账号计划类型，例如 `TEAM`
- `5小时`：当前 5 小时额度剩余百分比和下次重置时间
- `每周`：当前每周额度剩余百分比和下次重置时间
- `[当前]`：当前正在使用的账号

底部操作：

- `Enter`：刷新当前页面
- 输入 `#` 序号：切换到对应账号
- 输入 `S`：存档当前账号（仅在当前账号尚未存档时显示）
- 输入 `0`：退出工具

## Agent / CLI Commands

以下命令更适合 Agent、脚本或无交互场景：

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

# 切换结果用 JSON 返回（适合 Agent）
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
3. 再按邮箱升序作为最终 tie-breaker

## 给 Agent 的可复制提示词

下面这段提示词可以直接复制给任意 Agent：

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

## Project Structure

```text
CJFCodexSwitcher/
├── codex_switcher.py                      # 主实现模块
├── codex-switcher.py                      # 命令入口包装器
├── install.py                             # 本地安装脚本
├── pyproject.toml                         # Python 打包与 console script 入口
├── README.md                              # 用户文档
├── .codex/skills/codex-switcher-help/     # 项目内 Skill
└── openspec/                              # 需求与变更文档
```

## Security Notes

- 本仓库不会提交你的本地账号快照、usage 缓存、备份文件或运行时脚本
- 真实账号数据保存在本机本地目录，例如 `accounts/`、`usage_cache/`、`backups/`
- 如果你 fork 或二次发布本仓库，请保持这些目录继续被 `.gitignore` 排除

## Contributing

欢迎提交 Issue 或 PR。提交前建议：

1. 先运行交互页面确认 UI 行为正常
2. 运行非交互 CLI 命令确认 JSON 输出可用
3. 如果改动影响工作流，更新项目内 Skill 和 README

## Release

首个公开版本 release notes：

- [v0.1.0 Release Notes](docs/releases/v0.1.0.md)

## License

MIT
