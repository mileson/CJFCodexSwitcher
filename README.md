# CJFCodexSwitcher

Fast switching and quota inspection for multiple Codex accounts.

[简体中文](./README_CN.md)

[![Release](https://img.shields.io/github/v/release/mileson/CJFCodexSwitcher?display_name=tag)](https://github.com/mileson/CJFCodexSwitcher/releases)
[![License](https://img.shields.io/github/license/mileson/CJFCodexSwitcher)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![Homebrew](https://img.shields.io/badge/Homebrew-installable-FBB040?logo=homebrew&logoColor=black)](https://github.com/mileson/homebrew-cjfcodexswitcher)
[![GitHub Stars](https://img.shields.io/github/stars/mileson/CJFCodexSwitcher?style=social)](https://github.com/mileson/CJFCodexSwitcher/stargazers)
[![Last Commit](https://img.shields.io/github/last-commit/mileson/CJFCodexSwitcher)](https://github.com/mileson/CJFCodexSwitcher/commits/main)
[![Downloads](https://img.shields.io/github/downloads/mileson/CJFCodexSwitcher/total)](https://github.com/mileson/CJFCodexSwitcher/releases)

![CJFCodexSwitcher Screenshot](docs/images/overview.png)

## What It Does

`CJFCodexSwitcher` is a CLI/TUI tool for people who use multiple Codex accounts and need to:

- inspect live 5-hour and weekly quota windows
- switch accounts quickly from a ranked list
- automate account selection through stable non-interactive CLI commands

## Features

- Direct startup into the live account list
- Active account shown at the top and separated from the rest
- Live refresh of quota windows and reset times
- Automatic snapshot save for the current account when needed
- Add a new account directly from the quota view via the official `codex login` flow
- Agent-friendly CLI: `--list`, `--json`, `--best`, `--switch`, `--save-current`
- Homebrew and `pipx` friendly distribution
- Repository-local skill for guided agent usage

## Tech Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3 |
| Network | Python stdlib `urllib` |
| Packaging | `pyproject.toml` + `setuptools` |
| UI | Terminal TUI |

## One-Line Install

```bash
brew tap mileson/cjfcodexswitcher && brew install cjfcodexswitcher
```

```bash
pipx install git+https://github.com/mileson/CJFCodexSwitcher.git
```

If you do not use `pipx`:

```bash
python3 -m pip install "git+https://github.com/mileson/CJFCodexSwitcher.git"
```

## Quick Start

Requirements:

- Python 3.8+
- A working `codex` CLI on your machine

Install from source:

```bash
git clone https://github.com/mileson/CJFCodexSwitcher.git
cd CJFCodexSwitcher
python3 install.py
source ~/.zshrc  # or ~/.bashrc
codex-switcher
```

## Interactive Usage

The tool opens directly into the live account view.

Key fields:

- `邮箱`: account email
- `PLAN`: plan type such as `TEAM`
- `5小时`: 5-hour remaining amount and next reset time
- `每周`: weekly remaining amount and next reset time
- `[当前]`: the active account, shown first

Bottom actions:

- `Enter`: refresh current page
- `a`: start the official `codex login` flow, then auto-save the authenticated account and keep it active
- `#`: switch to the selected account
- `0`: exit the tool

Notes:

- If the current account is not archived yet, entering the live quota view will save it automatically
- The add-account flow reuses the official browser login from `codex login`; in headless environments you can use `codex login --device-auth`

## Agent / CLI Commands

```bash
codex-switcher --list
codex-switcher --list --json
codex-switcher --best
codex-switcher --best --json
codex-switcher --switch 2
codex-switcher --switch user@example.com
codex-switcher --switch best
codex-switcher --switch best --json
codex-switcher --save-current
codex-switcher --refresh
```

Ranking rule:

1. Sort by 5-hour remaining count descending
2. If tied, sort by weekly remaining count descending
3. Use email ascending as the final tie-breaker

## Agent Prompt

Use the repository-local skill:

```text
/Users/mileson/codex-switcher/.codex/skills/codex-switcher-help/SKILL.md
```

Then prefer non-interactive commands such as `--list --json`, `--best --json`, and `--switch best --json`.

## Project Structure

```text
CJFCodexSwitcher/
├── codex_switcher.py
├── codex-switcher.py
├── install.py
├── pyproject.toml
├── README.md
├── README_CN.md
├── .codex/skills/codex-switcher-help/
└── docs/
```

## Security

See [SECURITY.md](./SECURITY.md).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## Release

Current recommended release notes:

- [v0.1.7 Release Notes](docs/releases/v0.1.7.md)

## License

MIT
