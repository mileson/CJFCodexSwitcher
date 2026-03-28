#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex Switcher - 跨平台 Codex 账号管理工具

功能:
  (1) 查看所有账号余量（包括 5小时/每周限额）
  (2) 切换账号
  (3) 存档当前登录账号
  (4) 刷新使用量（通过浏览器）
  (0) 退出

支持平台: macOS, Linux, Windows
"""

import os
import sys
import argparse
import json
import shlex
import re
import shutil
import subprocess
import base64
import platform
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import unicodedata
from typing import Optional, Dict, List, Tuple, Any

REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token"
REFRESH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REFRESH_LOOKAHEAD_SECONDS = 300
TOKEN_REFRESH_INTERVAL_DAYS = 8
USAGE_API_URL = "https://chatgpt.com/backend-api/wham/usage"
RESTART_DRY_RUN_ENV = "CODEX_SWITCHER_DRY_RUN_RESTART"
MAX_REFRESH_WORKERS = 6
ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*m')

# ============== 跨平台路径配置 ==============

def get_home_dir() -> Path:
    """获取用户主目录"""
    return Path.home()

def get_codex_config_dir() -> Path:
    """获取 Codex 配置目录"""
    home = get_home_dir()
    if platform.system() == "Windows":
        return home / ".codex"
    else:
        return home / ".codex"

def get_switcher_dir() -> Path:
    """获取 Codex Switcher 数据目录"""
    home = get_home_dir()
    if platform.system() == "Windows":
        return home / "codex-switcher"
    else:
        return home / "codex-switcher"

def get_accounts_dir() -> Path:
    """获取账号存档目录"""
    return get_switcher_dir() / "accounts"

def get_usage_cache_dir() -> Path:
    """获取使用量缓存目录"""
    return get_switcher_dir() / "usage_cache"

def get_auth_file() -> Path:
    """获取当前 auth.json 文件路径"""
    return get_codex_config_dir() / "auth.json"

# ============== 颜色配置 ==============

class Colors:
    """终端颜色（跨平台兼容）"""
    SUPPORTS_COLOR = (
        hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() and
        (platform.system() != 'Windows' or 'ANSICON' in os.environ or
         'WT_SESSION' in os.environ or os.environ.get('TERM') == 'xterm')
    )

    if SUPPORTS_COLOR:
        HEADER = '\033[95m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        DIM = '\033[2m'
        UNDERLINE = '\033[4m'
    else:
        HEADER = BLUE = CYAN = GREEN = YELLOW = RED = ENDC = BOLD = DIM = UNDERLINE = ''

# ============== 工具函数 ==============

def clear_screen():
    """清屏（跨平台）"""
    os.system('cls' if platform.system() == 'Windows' else 'clear')

def decode_jwt_payload(token: str) -> Optional[dict]:
    """解码 JWT token 的 payload 部分"""
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return None

def format_datetime(dt_str: str) -> str:
    """格式化日期时间"""
    if not dt_str:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%m-%d %H:%M')
    except:
        return dt_str[:16] if len(dt_str) > 16 else dt_str

def time_until_reset(sub_until: str) -> str:
    """计算到重置还有多久"""
    if not sub_until:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(sub_until.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = dt - now

        if delta.total_seconds() < 0:
            return "已过期"

        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60

        if days > 0:
            return f"{days}d{hours}h"
        elif hours > 0:
            return f"{hours}h{minutes}m"
        else:
            return f"{minutes}m"
    except:
        return 'N/A'

def get_token_status(exp: int) -> Tuple[str, str]:
    """获取 token 状态"""
    if not exp:
        return 'unknown', Colors.YELLOW

    now = time.time()
    remaining = exp - now

    if remaining <= 0:
        return 'expired', Colors.RED
    elif remaining < 3600:
        return 'expiring', Colors.YELLOW
    else:
        return 'valid', Colors.GREEN

def sanitize_key(value: str) -> str:
    """将任意字符串转换为安全文件名"""
    return "".join(c if c.isalnum() or c in '-_.' else '_' for c in value)

def char_display_width(ch: str) -> int:
    """计算单个字符在终端中的显示宽度"""
    if unicodedata.east_asian_width(ch) in ('W', 'F'):
        return 2
    return 1

def display_width(text: str) -> int:
    """计算字符串在终端中的显示宽度"""
    clean = ANSI_ESCAPE_RE.sub('', text)
    return sum(char_display_width(ch) for ch in clean)

def truncate_display_text(text: str, max_width: int, suffix: str = '..') -> str:
    """按终端显示宽度截断字符串"""
    if display_width(text) <= max_width:
        return text

    suffix_width = display_width(suffix)
    width = 0
    chars = []
    for ch in text:
        ch_width = char_display_width(ch)
        if width + ch_width + suffix_width > max_width:
            break
        chars.append(ch)
        width += ch_width
    return ''.join(chars) + suffix

def pad_display(text: str, width: int) -> str:
    """按终端显示宽度右侧补齐空格"""
    pad = max(0, width - display_width(text))
    return text + (' ' * pad)

def parse_iso_datetime(dt_str: str) -> Optional[datetime]:
    """解析 ISO 时间字符串"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except Exception:
        return None

def iso_utc_now() -> str:
    """返回当前 UTC 时间字符串"""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def extract_claims_from_id_token(id_token: str) -> Optional[dict]:
    """从 id_token 提取 claims"""
    payload = decode_jwt_payload(id_token)
    if not payload:
        return None
    auth_info = payload.get('https://api.openai.com/auth', {})
    email = payload.get('email', 'Unknown')
    chatgpt_user_id = auth_info.get('chatgpt_user_id', '') or auth_info.get('user_id', '')
    account_id = auth_info.get('chatgpt_account_id', '')
    record_key = ''
    if chatgpt_user_id and account_id:
        record_key = f"{chatgpt_user_id}::{account_id}"

    return {
        'payload': payload,
        'auth_info': auth_info,
        'email': email,
        'chatgpt_user_id': chatgpt_user_id,
        'chatgpt_account_id': account_id,
        'record_key': record_key,
    }

def normalize_organizations(auth_info: dict) -> List[dict]:
    """Normalize workspace/organization metadata from auth claims."""
    raw_orgs = auth_info.get('organizations', [])
    if not isinstance(raw_orgs, list):
        return []

    organizations = []
    for raw_org in raw_orgs:
        if not isinstance(raw_org, dict):
            continue

        organizations.append({
            'id': str(raw_org.get('id', '') or '').strip(),
            'title': str(raw_org.get('title', '') or '').strip(),
            'role': str(raw_org.get('role', '') or '').strip(),
            'is_default': bool(raw_org.get('is_default')),
        })
    return organizations

def get_primary_workspace(organizations: List[dict]) -> dict:
    """Pick the default workspace when available, otherwise the first one."""
    for org in organizations:
        if org.get('is_default'):
            return org
    return organizations[0] if organizations else {}

def format_workspace_display(organizations: List[dict], primary: dict) -> str:
    """Build a short label for CLI and table output."""
    if not primary:
        return 'Unknown'

    label = primary.get('title') or primary.get('id') or 'Unknown'
    extra_count = max(0, len(organizations) - 1)
    if extra_count:
        return f"{label} (+{extra_count})"
    return label

def list_windows_processes() -> List[dict]:
    """List Windows processes with executable path and command line details."""
    if platform.system() != 'Windows':
        return []

    script = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    raw = result.stdout.strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except Exception:
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    processes = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get('ProcessId') or 0)
            ppid = int(item.get('ParentProcessId') or 0)
        except Exception:
            continue
        if pid <= 0:
            continue

        processes.append({
            'pid': pid,
            'ppid': ppid,
            'name': str(item.get('Name') or ''),
            'exe_path': str(item.get('ExecutablePath') or ''),
            'command_line': str(item.get('CommandLine') or ''),
        })
    return processes

def get_usage_cache_key(email: str, account_id: str = '', record_key: str = '') -> str:
    """生成 usage 缓存 key"""
    if record_key:
        return sanitize_key(record_key)
    if email and account_id:
        return sanitize_key(f"{email}__{account_id}")
    if email:
        return sanitize_key(email)
    if account_id:
        return sanitize_key(account_id)
    return 'unknown'

def list_processes() -> List[Tuple[int, str]]:
    """列出当前用户进程"""
    try:
        result = subprocess.run(
            ['ps', '-axo', 'pid=,command='],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []

    processes = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            pid_text, command = line.split(None, 1)
            processes.append((int(pid_text), command))
        except ValueError:
            continue
    return processes

def list_process_tree() -> Dict[int, Tuple[int, str]]:
    """列出当前用户进程树"""
    try:
        result = subprocess.run(
            ['ps', '-axo', 'pid=,ppid=,command='],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return {}

    tree: Dict[int, Tuple[int, str]] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            pid_text, ppid_text, command = line.split(None, 2)
            tree[int(pid_text)] = (int(ppid_text), command)
        except ValueError:
            continue
    return tree

def get_process_cwd(pid: int) -> str:
    """获取进程当前工作目录"""
    try:
        result = subprocess.run(
            ['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return str(get_home_dir())

    for line in result.stdout.splitlines():
        if line.startswith('n') and len(line) > 1:
            return line[1:]
    return str(get_home_dir())

def detect_codex_desktop_instances() -> List[dict]:
    if platform.system() == 'Windows':
        instances = []
        for proc in list_windows_processes():
            exe_path = (proc.get('exe_path') or '').replace('/', '\\')
            command = proc.get('command_line', '')
            if not exe_path.lower().endswith('\\app\\codex.exe'):
                continue
            if '\\resources\\codex.exe' in exe_path.lower():
                continue
            if '--type=' in command:
                continue
            instances.append({
                'pid': proc['pid'],
                'app_path': exe_path,
            })
        return instances
    """检测运行中的 Codex Desktop 主进程"""
    instances = []
    for pid, command in list_processes():
        if '/Contents/MacOS/Codex' not in command:
            continue
        if 'Codex Helper' in command:
            continue
        if 'codex-switcher.py' in command:
            continue

        app_path = command.split('/Contents/MacOS/Codex', 1)[0]
        if app_path.endswith('.app'):
            instances.append({
                'pid': pid,
                'app_path': app_path,
            })
    return instances

def detect_codex_cli_instances() -> List[dict]:
    if platform.system() == 'Windows':
        return []
    """检测运行中的 codex CLI 进程"""
    tree = list_process_tree()
    instances = []
    for pid, (ppid, command) in tree.items():
        binary = command.split(' ', 1)[0]
        if os.path.basename(binary) != 'codex':
            continue
        if '/Applications/Codex.app/Contents/Resources/codex' in command:
            continue
        if pid == os.getpid():
            continue
        if process_is_managed_by_codex_desktop(pid, tree):
            continue

        instances.append({
            'pid': pid,
            'command': command,
            'cwd': get_process_cwd(pid),
        })
    return instances

def process_is_managed_by_codex_desktop(
    pid: int,
    tree: Dict[int, Tuple[int, str]],
) -> bool:
    """判断进程是否属于 Codex Desktop 进程树"""
    visited = set()
    current = pid

    while current and current not in visited:
        visited.add(current)
        node = tree.get(current)
        if not node:
            return False
        parent_pid, command = node
        if '/Applications/Codex.app/' in command:
            return True
        current = parent_pid

    return False

def escape_applescript_string(value: str) -> str:
    """转义 AppleScript 字符串"""
    return value.replace('\\', '\\\\').replace('"', '\\"')

def escape_powershell_string(value: str) -> str:
    """Escape a string for single-quoted PowerShell literals."""
    return value.replace("'", "''")

def collect_windows_restart_targets(desktop_instances: List[dict]) -> List[str]:
    """Collect executable paths that should be closed during Windows restart."""
    targets = []
    seen = set()
    for item in desktop_instances:
        app_path = str(item.get('app_path') or '')
        if not app_path:
            continue

        for candidate in [app_path, str(Path(app_path).parent / 'resources' / 'codex.exe')]:
            normalized = candidate.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            targets.append(candidate)
    return targets

def build_restart_script(
    script_path: Path,
    desktop_instances: List[dict],
    cli_instances: List[dict],
) -> str:
    """构建重启脚本内容"""
    lines = [
        '#!/bin/zsh',
        'sleep 1',
    ]

    desktop_pids = [str(item['pid']) for item in desktop_instances]
    cli_pids = [str(item['pid']) for item in cli_instances]
    if desktop_pids:
        lines.append(f"kill -TERM {' '.join(desktop_pids)} >/dev/null 2>&1 || true")
    if cli_pids:
        lines.append(f"kill -TERM {' '.join(cli_pids)} >/dev/null 2>&1 || true")

    lines.append('sleep 1')

    for item in desktop_instances:
        lines.append(f"open -na {shlex.quote(item['app_path'])} >/dev/null 2>&1 || true")

    lines.append(f"rm -f {shlex.quote(str(script_path))}")
    return '\n'.join(lines) + '\n'

def build_windows_restart_script(script_path: Path, desktop_instances: List[dict]) -> str:
    """Build a PowerShell script that restarts Codex Desktop on Windows."""
    desktop_pids = [str(int(item['pid'])) for item in desktop_instances if item.get('pid')]
    restart_paths = []
    seen_paths = set()
    for item in desktop_instances:
        app_path = str(item.get('app_path') or '')
        if not app_path:
            continue
        normalized = app_path.lower()
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        restart_paths.append(app_path)

    target_paths = collect_windows_restart_targets(desktop_instances)
    escaped_target_paths = ', '.join(
        f"'{escape_powershell_string(path)}'" for path in target_paths
    ) or "''"
    escaped_restart_paths = ', '.join(
        f"'{escape_powershell_string(path)}'" for path in restart_paths
    ) or "''"
    escaped_script_path = escape_powershell_string(str(script_path))

    lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        "Start-Sleep -Seconds 1",
        f"$desktopPids = @({', '.join(desktop_pids)})" if desktop_pids else "$desktopPids = @()",
        f"$targetPaths = @({escaped_target_paths})",
        f"$restartPaths = @({escaped_restart_paths})",
        "foreach ($pid in $desktopPids) { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue }",
        "$lookup = @{}",
        "foreach ($path in $targetPaths) { if ($path) { $lookup[$path.ToLowerInvariant()] = $true } }",
        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $lookup.ContainsKey($_.ExecutablePath.ToLowerInvariant()) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        "Start-Sleep -Seconds 1",
        "foreach ($path in $restartPaths) { if ($path -and (Test-Path -LiteralPath $path)) { Start-Process -FilePath $path | Out-Null } }",
        f"Remove-Item -LiteralPath '{escaped_script_path}' -Force -ErrorAction SilentlyContinue",
    ]
    return '\r\n'.join(lines) + '\r\n'

def schedule_codex_restart() -> Tuple[bool, bool, str]:
    """安排后台重启运行中的 Codex Desktop 和 CLI"""
    current_platform = platform.system()
    if current_platform not in {'Darwin', 'Windows'}:
        return False, False, '自动重启目前仅支持 macOS'

    desktop_instances = detect_codex_desktop_instances()
    cli_instances = detect_codex_cli_instances()
    if not desktop_instances and not cli_instances:
        return False, False, '未检测到运行中的 Codex 客户端或 Codex CLI'

    runtime_dir = get_switcher_dir() / 'runtime'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    if current_platform == 'Windows':
        script_path = runtime_dir / f"restart_codex_{int(time.time())}.ps1"
        script_path.write_text(
            build_windows_restart_script(script_path, desktop_instances),
            encoding='utf-8',
        )
    else:
        script_path = runtime_dir / f"restart_codex_{int(time.time())}.sh"
        script_path.write_text(
            build_restart_script(script_path, desktop_instances, cli_instances),
            encoding='utf-8',
        )
        script_path.chmod(0o700)

    dry_run = os.environ.get(RESTART_DRY_RUN_ENV) == '1'
    if dry_run:
        message = (
            f"[dry-run] 将关闭 Codex 客户端及相关 CLI 进程，"
            f"并重启 {len(desktop_instances)} 个 Codex 客户端，会话脚本: {script_path}"
        )
        return True, True, message

    if current_platform == 'Windows':
        subprocess.Popen(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    else:
        subprocess.Popen(
            ['/bin/zsh', str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    message = (
        f"已安排关闭 Codex 客户端及相关 CLI 进程，并重启 {len(desktop_instances)} 个 Codex 客户端"
    )
    return True, False, message

def finish_switch_with_restart(quiet: bool = False) -> dict:
    """切换账号后安排自动重启"""
    scheduled, dry_run, message = schedule_codex_restart()
    if scheduled:
        if not quiet:
            print(f"{Colors.DIM}  {message}{Colors.ENDC}")
            if not dry_run:
                print(f"{Colors.DIM}  正在关闭并重启 Codex 客户端，请稍候...{Colors.ENDC}")
        return {'scheduled': True, 'dry_run': dry_run, 'message': message}

    if not quiet:
        print(f"{Colors.YELLOW}  {message}{Colors.ENDC}")
        print(f"{Colors.DIM}  提示: 请重启 Codex 或新开终端使登录生效{Colors.ENDC}")
    return {'scheduled': False, 'dry_run': False, 'message': message}

# ============== 使用量缓存 ==============

def get_usage_cache_file(email: str, account_id: str = '', record_key: str = '') -> Path:
    """获取使用量缓存文件路径"""
    cache_key = get_usage_cache_key(email, account_id, record_key)
    return get_usage_cache_dir() / f"usage_{cache_key}.json"

def load_usage_cache(email: str, account_id: str = '', record_key: str = '') -> Optional[dict]:
    """加载使用量缓存"""
    candidates = [get_usage_cache_file(email, account_id, record_key)]
    legacy_cache = get_usage_cache_dir() / f"usage_{sanitize_key(email)}.json" if email else None
    if legacy_cache and legacy_cache not in candidates:
        candidates.append(legacy_cache)

    for cache_file in candidates:
        if not cache_file.exists():
            continue
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 检查缓存是否过期（5分钟）
            if time.time() - data.get('timestamp', 0) > 300:
                continue
            return data
        except Exception:
            continue
    return None

def save_usage_cache(email: str, usage_data: dict, account_id: str = '', record_key: str = ''):
    """保存使用量缓存"""
    cache_dir = get_usage_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = get_usage_cache_file(email, account_id, record_key)
    payload = dict(usage_data)
    payload['timestamp'] = time.time()
    payload['email'] = email
    payload['account_id'] = account_id
    payload['record_key'] = record_key
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass

# ============== Auth 快照读写 ==============

def load_auth_data_from_path(auth_path: Path) -> Optional[dict]:
    """加载指定 auth 文件"""
    if not auth_path.exists():
        return None
    try:
        with open(auth_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def save_auth_data_to_path(auth_path: Path, auth_data: dict) -> bool:
    """保存指定 auth 文件"""
    try:
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        with open(auth_path, 'w', encoding='utf-8') as f:
            json.dump(auth_data, f, indent=2)
            f.write('\n')
        return True
    except Exception:
        return False

def merge_refreshed_tokens(auth_data: dict, refreshed_tokens: dict) -> dict:
    """将刷新后的 token 合并到 auth 数据"""
    merged = dict(auth_data)
    tokens = dict(merged.get('tokens', {}))
    claims = extract_claims_from_id_token(refreshed_tokens.get('id_token', '') or tokens.get('id_token', ''))

    for key in ('id_token', 'access_token', 'refresh_token'):
        value = refreshed_tokens.get(key)
        if value:
            tokens[key] = value

    account_id = refreshed_tokens.get('account_id')
    if not account_id and claims:
        account_id = claims.get('chatgpt_account_id', '')
    if account_id:
        tokens['account_id'] = account_id

    merged['tokens'] = tokens
    merged['last_refresh'] = iso_utc_now()
    return merged

def mirror_auth_tokens_to_path(auth_path: Path, refreshed_auth_data: dict) -> bool:
    """将刷新后的 token 字段同步到其他同账号文件"""
    existing = load_auth_data_from_path(auth_path)
    if not existing:
        return False
    merged = merge_refreshed_tokens(existing, refreshed_auth_data.get('tokens', {}))
    if refreshed_auth_data.get('last_refresh'):
        merged['last_refresh'] = refreshed_auth_data.get('last_refresh')
    return save_auth_data_to_path(auth_path, merged)

def parse_refresh_error(body: str) -> Tuple[str, str]:
    """解析 refresh token 错误"""
    backend_code = ''
    message = 'token 刷新失败'
    try:
        payload = json.loads(body) if body else {}
    except Exception:
        payload = {}

    if isinstance(payload, dict):
        error = payload.get('error')
        if isinstance(error, dict):
            backend_code = str(error.get('code', '') or '')
        elif isinstance(error, str):
            backend_code = error
        backend_code = backend_code.lower()
        message = str(
            payload.get('error_description')
            or payload.get('message')
            or payload.get('detail')
            or message
        )

    if backend_code == 'refresh_token_expired':
        return 'reauth', 'refresh token 已过期'
    if backend_code == 'refresh_token_reused':
        return 'reauth', 'refresh token 已被轮换'
    if backend_code == 'refresh_token_invalidated':
        return 'reauth', 'refresh token 已失效'
    return 'error', message

def refresh_tokens_via_oauth(refresh_token: str) -> Tuple[Optional[dict], str]:
    """通过 OpenAI OAuth 刷新 token"""
    payload = json.dumps({
        'client_id': REFRESH_CLIENT_ID,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'codex-switcher',
    }
    req = urllib.request.Request(REFRESH_TOKEN_URL, data=payload, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        refreshed = {
            'id_token': data.get('id_token', ''),
            'access_token': data.get('access_token', ''),
            'refresh_token': data.get('refresh_token', ''),
        }
        if not any(refreshed.values()):
            return None, 'empty_refresh_response'
        return refreshed, ''
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:1000] if e.fp else ''
        status, message = parse_refresh_error(body)
        if e.code == 401:
            return None, status
        return None, message or f'HTTP {e.code}'
    except Exception as e:
        return None, str(e)

# ============== API 获取使用量 ==============

import urllib.request
import urllib.error

def token_expired_or_expiring(access_token: str, last_refresh: str = '') -> bool:
    """判断 access_token 是否需要刷新"""
    if not access_token:
        return True

    payload = decode_jwt_payload(access_token) or {}
    exp = payload.get('exp', 0)
    now = time.time()
    if exp and exp <= now + REFRESH_LOOKAHEAD_SECONDS:
        return True

    last_refresh_dt = parse_iso_datetime(last_refresh)
    if last_refresh_dt and last_refresh_dt < datetime.now(timezone.utc) - timedelta(days=TOKEN_REFRESH_INTERVAL_DAYS):
        return True

    return False

def request_usage_payload(access_token: str, account_id: str) -> Tuple[Optional[dict], Optional[int], str]:
    """请求 usage API 原始响应"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'ChatGPT-Account-Id': account_id,
        'User-Agent': 'codex-auth',
        'Accept': 'application/json',
        'Accept-Encoding': 'identity',
    }

    req = urllib.request.Request(USAGE_API_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode()), resp.getcode(), ''
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:1000] if e.fp else ''
        return None, e.code, error_body
    except Exception as e:
        return None, None, str(e)

def build_usage_data(data: dict) -> Optional[dict]:
    """解析 usage API 响应"""
    rate_limit = data.get('rate_limit', {})
    primary = rate_limit.get('primary_window', {})
    secondary = rate_limit.get('secondary_window', {})
    plan_type = str(data.get('plan_type', 'unknown') or 'unknown')

    if not primary and not secondary:
        return None

    is_team_family = plan_type in {'team', 'business', 'enterprise', 'edu'}
    hourly_max = 80 if is_team_family else 50
    weekly_max = 500 if is_team_family else 100

    usage_data = {
        'hourly_used': 'N/A',
        'hourly_limit': str(hourly_max),
        'hourly_remaining': 'N/A',
        'hourly_percent': 0,
        'weekly_used': 'N/A',
        'weekly_limit': str(weekly_max),
        'weekly_remaining': 'N/A',
        'weekly_percent': 0,
        'next_reset': 'N/A',
        'next_reset_weekly': 'N/A',
        'reset_at_hourly': 0,
        'reset_at_weekly': 0,
        'plan_type': plan_type,
    }

    # 5小时限额
    if primary:
        used_percent = primary.get('used_percent', 0)
        used = int(hourly_max * used_percent / 100)
        remaining = hourly_max - used
        reset_at = int(primary.get('reset_at', 0) or 0)

        usage_data['hourly_used'] = str(used)
        usage_data['hourly_remaining'] = str(remaining)
        usage_data['hourly_percent'] = used_percent
        usage_data['reset_at_hourly'] = reset_at
        usage_data['next_reset'] = format_reset_time(reset_at)

    # 每周限额
    if secondary:
        used_percent = secondary.get('used_percent', 0)
        used = int(weekly_max * used_percent / 100)
        remaining = weekly_max - used
        reset_at = int(secondary.get('reset_at', 0) or 0)

        usage_data['weekly_used'] = str(used)
        usage_data['weekly_remaining'] = str(remaining)
        usage_data['weekly_percent'] = used_percent
        usage_data['reset_at_weekly'] = reset_at
        usage_data['next_reset_weekly'] = format_reset_time(reset_at)

    return usage_data

def attempt_token_refresh(auth_path: Path, auth_data: dict) -> Tuple[Optional[dict], str]:
    """尝试刷新单个 auth 快照的 token"""
    tokens = auth_data.get('tokens', {})
    refresh_token = tokens.get('refresh_token', '')
    if not refresh_token:
        return None, 'missing_refresh_token'

    refreshed_tokens, status = refresh_tokens_via_oauth(refresh_token)
    if not refreshed_tokens:
        return None, status or 'refresh_failed'

    updated_auth = merge_refreshed_tokens(auth_data, refreshed_tokens)
    if not save_auth_data_to_path(auth_path, updated_auth):
        return None, 'save_failed'
    return updated_auth, 'refreshed'

def refresh_usage_for_auth_path(auth_path: Path) -> Optional[dict]:
    """为指定 auth 文件刷新 usage，并在必要时刷新 token"""
    auth_data = load_auth_data_from_path(auth_path)
    if not auth_data:
        return None

    info = get_account_info(auth_data, str(auth_path))
    if not info:
        return None

    if token_expired_or_expiring(info.get('access_token', ''), info.get('last_refresh', '')):
        updated_auth, refresh_status = attempt_token_refresh(auth_path, auth_data)
        if updated_auth:
            auth_data = updated_auth
            info = get_account_info(auth_data, str(auth_path))
        elif refresh_status == 'reauth':
            info['refresh_status'] = 'reauth'
            info['refresh_status_text'] = '需重登'
            return info

    access_token = info.get('access_token', '')
    account_id = info.get('account_id', '')
    payload, status_code, _ = request_usage_payload(access_token, account_id)
    if payload:
        usage_data = build_usage_data(payload)
        if usage_data:
            save_usage_cache(
                info.get('email', ''),
                usage_data,
                info.get('account_id', ''),
                info.get('record_key', ''),
            )
            info = get_account_info(load_auth_data_from_path(auth_path) or auth_data, str(auth_path))
            info['refresh_status'] = 'fresh'
            info['refresh_status_text'] = '已刷新'
            return info

    if status_code in (401, 403):
        updated_auth, refresh_status = attempt_token_refresh(auth_path, auth_data)
        if updated_auth:
            auth_data = updated_auth
            info = get_account_info(auth_data, str(auth_path))
            payload, _, _ = request_usage_payload(info.get('access_token', ''), info.get('account_id', ''))
            if payload:
                usage_data = build_usage_data(payload)
                if usage_data:
                    save_usage_cache(
                        info.get('email', ''),
                        usage_data,
                        info.get('account_id', ''),
                        info.get('record_key', ''),
                    )
                    info = get_account_info(auth_data, str(auth_path))
                    info['refresh_status'] = 'fresh'
                    info['refresh_status_text'] = '已刷新'
                    return info
        if refresh_status == 'reauth':
            info['refresh_status'] = 'reauth'
            info['refresh_status_text'] = '需重登'
        else:
            info['refresh_status'] = 'cached'
            info['refresh_status_text'] = '缓存'
        return info

    cached_info = get_account_info(auth_data, str(auth_path)) or info
    cached_info['refresh_status'] = 'cached'
    cached_info['refresh_status_text'] = '缓存'
    return cached_info

def fetch_usage_via_api(email: str, access_token: str, account_id: str) -> Optional[dict]:
    """通过 ChatGPT 后端 API 获取使用量信息"""
    print(f"{Colors.CYAN}正在获取使用量...{Colors.ENDC}")
    print(f"{Colors.DIM}账号: {email}{Colors.ENDC}")

    payload, status_code, error = request_usage_payload(access_token, account_id)
    if payload:
        usage_data = build_usage_data(payload)
        if usage_data:
            save_usage_cache(email, usage_data, account_id)
            print(f"{Colors.GREEN}  ✓ 获取成功！{Colors.ENDC}")
            return usage_data

    if status_code:
        print(f"{Colors.RED}  ✗ API 请求失败: HTTP {status_code}{Colors.ENDC}")
        if status_code == 401:
            print(f"{Colors.YELLOW}  Token 已过期，请重新登录{Colors.ENDC}")
        elif status_code == 403:
            print(f"{Colors.YELLOW}  无权限访问，请检查账号状态{Colors.ENDC}")
    elif error:
        print(f"{Colors.RED}  ✗ 获取失败: {error}{Colors.ENDC}")
    return None

# ============== 账号管理 ==============

def get_account_info(auth_data: dict, file_path: str = '') -> Optional[dict]:
    """从 auth.json 数据中提取账号信息"""
    tokens = auth_data.get('tokens', {})
    id_token = tokens.get('id_token', '')
    access_token = tokens.get('access_token', '')
    refresh_token = tokens.get('refresh_token', '')

    if not id_token:
        return None

    claims = extract_claims_from_id_token(id_token)
    if not claims:
        return None

    payload = claims.get('payload', {})
    auth_info = claims.get('auth_info', {})
    email = claims.get('email', 'Unknown')
    account_id = tokens.get('account_id', '') or claims.get('chatgpt_account_id', '')
    chatgpt_user_id = claims.get('chatgpt_user_id', '')
    record_key = claims.get('record_key', '')
    organizations = normalize_organizations(auth_info)
    primary_workspace = get_primary_workspace(organizations)
    token_payload = decode_jwt_payload(access_token) or {}
    token_exp = token_payload.get('exp', 0) or payload.get('exp', 0)

    info = {
        'email': email,
        'name': payload.get('name', 'Unknown'),
        'plan_type': auth_info.get('chatgpt_plan_type', 'Unknown'),
        'account_id': account_id,
        'chatgpt_user_id': chatgpt_user_id,
        'record_key': record_key or (f"{email}::{account_id}" if email and account_id else file_path),
        'organizations': organizations,
        'workspace_title': primary_workspace.get('title', ''),
        'workspace_id': primary_workspace.get('id', ''),
        'workspace_role': primary_workspace.get('role', ''),
        'workspace_is_default': bool(primary_workspace.get('is_default')),
        'workspace_display': format_workspace_display(organizations, primary_workspace),
        'sub_active_start': auth_info.get('chatgpt_subscription_active_start', ''),
        'sub_active_until': auth_info.get('chatgpt_subscription_active_until', ''),
        'last_refresh': auth_data.get('last_refresh', ''),
        'token_exp': token_exp,
        'access_token': access_token,
        'refresh_token': refresh_token,
        'file_path': file_path,
        'refresh_status': 'unknown',
        'refresh_status_text': '未刷新',
    }

    # 尝试加载使用量缓存
    usage_cache = load_usage_cache(email, account_id, info['record_key'])
    if usage_cache:
        info.update({
            'hourly_limit': usage_cache.get('hourly_limit', '?'),
            'hourly_used': usage_cache.get('hourly_used', '?'),
            'hourly_remaining': usage_cache.get('hourly_remaining', '?'),
            'hourly_percent': usage_cache.get('hourly_percent', 0),
            'weekly_limit': usage_cache.get('weekly_limit', '?'),
            'weekly_used': usage_cache.get('weekly_used', '?'),
            'weekly_remaining': usage_cache.get('weekly_remaining', '?'),
            'weekly_percent': usage_cache.get('weekly_percent', 0),
            'next_reset': usage_cache.get('next_reset', '?'),
            'next_reset_weekly': usage_cache.get('next_reset_weekly', '?'),
            'reset_at_hourly': usage_cache.get('reset_at_hourly', 0),
            'reset_at_weekly': usage_cache.get('reset_at_weekly', 0),
        })
    else:
        info.update({
            'hourly_limit': '?',
            'hourly_used': '?',
            'hourly_remaining': '?',
            'hourly_percent': 0,
            'weekly_limit': '?',
            'weekly_used': '?',
            'weekly_remaining': '?',
            'weekly_percent': 0,
            'next_reset': '?',
            'next_reset_weekly': '?',
            'reset_at_hourly': 0,
            'reset_at_weekly': 0,
        })

    return info

def load_current_auth() -> Optional[dict]:
    """加载当前 auth.json"""
    return load_auth_data_from_path(get_auth_file())

def save_current_auth(name: str) -> bool:
    """存档当前登录账号"""
    auth_file = get_auth_file()
    if not auth_file.exists():
        return False

    accounts_dir = get_accounts_dir()
    accounts_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)

    target_file = accounts_dir / f"auth_{safe_name}.json"
    if target_file.exists():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        target_file = accounts_dir / f"auth_{safe_name}_{timestamp}.json"

    try:
        shutil.copy2(auth_file, target_file)
        return True
    except Exception:
        return False

def list_saved_accounts() -> List[dict]:
    """列出所有已存档的账号"""
    accounts_dir = get_accounts_dir()
    if not accounts_dir.exists():
        return []

    accounts = []
    for auth_file in sorted(accounts_dir.glob('auth_*.json')):
        try:
            auth_data = load_auth_data_from_path(auth_file)
            if not auth_data:
                continue
            info = get_account_info(auth_data, str(auth_file))
            if info:
                name = auth_file.stem.replace('auth_', '')
                info['saved_name'] = name
                info['file_path'] = str(auth_file)
                accounts.append(info)
        except Exception:
            continue

    return accounts

def switch_to_account(account_file: str) -> bool:
    """切换到指定账号"""
    auth_file = get_auth_file()

    if auth_file.exists():
        backup_dir = get_switcher_dir() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f"auth_backup_{timestamp}.json"
        try:
            shutil.copy2(auth_file, backup_file)
        except Exception:
            pass

    try:
        shutil.copy2(account_file, auth_file)
        return True
    except Exception:
        return False

# ============== 界面 ==============

def print_header():
    """打印标题"""
    width = 60
    print()
    print(f"{Colors.BOLD}{'═' * width}{Colors.ENDC}")
    print(f"{Colors.BOLD}  Codex Switcher - 账号管理工具{Colors.ENDC}")
    print(f"{Colors.BOLD}{'═' * width}{Colors.ENDC}")

def print_menu():
    """打印主菜单"""
    print()
    print(f"{Colors.CYAN}(1) 查看所有账号余量{Colors.ENDC}")
    print(f"{Colors.CYAN}(2) 切换账号{Colors.ENDC}")
    print(f"{Colors.CYAN}(3) 存档当前登录账号{Colors.ENDC}")
    print(f"{Colors.CYAN}(0) 退出{Colors.ENDC}")
    print()
    print(f"{Colors.DIM}{'─' * 60}{Colors.ENDC}")

def print_account_usage(acc: dict, show_detail: bool = True):
    """打印账号使用量详情"""
    email = acc.get('email', 'Unknown')
    name = acc.get('name', 'Unknown')
    plan = acc.get('plan_type', 'Unknown').upper()

    # 计划颜色
    if 'TEAM' in plan:
        plan_color = Colors.CYAN
    elif 'PLUS' in plan:
        plan_color = Colors.BLUE
    else:
        plan_color = Colors.DIM

    print(f"  邮箱:   {email}")
    print(f"  用户:   {name}")
    print(f"  计划:   {plan_color}{plan}{Colors.ENDC}")

    # 使用量信息 - 计算剩余百分比
    hourly_percent = acc.get('hourly_percent', 0)
    weekly_percent = acc.get('weekly_percent', 0)
    hourly_remaining_pct = 100 - hourly_percent if isinstance(hourly_percent, (int, float)) else 0
    weekly_remaining_pct = 100 - weekly_percent if isinstance(weekly_percent, (int, float)) else 0

    next_reset_hourly = acc.get('next_reset', '?')
    next_reset_weekly = acc.get('next_reset_weekly', '?')

    # 根据剩余百分比选择颜色
    def get_remaining_color(pct):
        if pct >= 50:
            return Colors.GREEN
        elif pct >= 20:
            return Colors.YELLOW
        else:
            return Colors.RED

    hourly_color = get_remaining_color(hourly_remaining_pct)
    weekly_color = get_remaining_color(weekly_remaining_pct)

    print(f"\n  {Colors.DIM}使用量:{Colors.ENDC}")
    print(f"  ├─ 5小时限额:  {hourly_color}剩余 {hourly_remaining_pct}%{Colors.ENDC}  (重置: {next_reset_hourly})")
    print(f"  └─ 每周限额:   {weekly_color}剩余 {weekly_remaining_pct}%{Colors.ENDC}  (重置: {next_reset_weekly})")

    # Token 状态
    exp = acc.get('token_exp', 0)
    status, status_color = get_token_status(exp)
    refresh_status = acc.get('refresh_status', 'unknown')
    refresh_text = acc.get('refresh_status_text', '未刷新')
    if refresh_status == 'fresh':
        refresh_color = Colors.GREEN
    elif refresh_status == 'reauth':
        refresh_color = Colors.RED
    else:
        refresh_color = Colors.YELLOW

    print(f"\n  Token:  {status_color}{status.upper()}{Colors.ENDC}")
    print(f"  刷新:   {refresh_color}{refresh_text}{Colors.ENDC}")

def print_current_account():
    """打印当前账号信息"""
    auth_data = load_current_auth()
    if not auth_data:
        print(f"{Colors.YELLOW}当前未登录任何账号{Colors.ENDC}")
        return None

    info = get_account_info(auth_data, str(get_auth_file()))
    if not info:
        print(f"{Colors.RED}无法解析当前账号信息{Colors.ENDC}")
        return None

    print()
    print(f"{Colors.BOLD}  当前登录账号{Colors.ENDC}")
    print(f"{Colors.DIM}  {'─' * 40}{Colors.ENDC}")
    print_account_usage(info)
    print()

    return info

def print_accounts_table(
    accounts: List[dict],
    title: str = "账号列表",
    highlight_current_first: bool = False,
):
    """打印账号表格（包含使用量）"""
    if not accounts:
        print(f"{Colors.YELLOW}没有找到任何账号{Colors.ENDC}")
        return

    email_width = 32
    space_width = 22
    hourly_width = 20
    weekly_width = 20
    plan_width = 6
    table_width = 2 + 2 + email_width + 1 + space_width + 1 + hourly_width + 1 + weekly_width + 1 + plan_width + 2

    print()
    print(f"{Colors.BOLD}  {title}{Colors.ENDC}")
    print(f"{Colors.DIM}  {'─' * table_width}{Colors.ENDC}")

    # 表头
    header = (
        f"  {pad_display('#', 2)} "
        f"{pad_display('邮箱', email_width)} "
        f"{pad_display('SPACE', space_width)} "
        f"{pad_display('PLAN', plan_width)} "
        f"{pad_display('5小时', hourly_width)} "
        f"{pad_display('每周', weekly_width)}"
    )
    print(f"{Colors.BOLD}{header}{Colors.ENDC}")
    print(f"{Colors.DIM}  {'─' * table_width}{Colors.ENDC}")

    current_rows = [acc for acc in accounts if acc.get('is_current')]
    other_rows = [acc for acc in accounts if not acc.get('is_current')]

    def render_row(i: int, acc: dict):
        email = acc.get('email', 'Unknown')
        if acc.get('is_current'):
            email = f"[当前] {email}"
        email = truncate_display_text(email, email_width)
        email_cell = pad_display(email, email_width)

        space_value = acc.get('workspace_title', '') or acc.get('workspace_display', '') or '-'
        space_value = truncate_display_text(space_value, space_width)
        space_cell = pad_display(space_value, space_width)

        plan = str(acc.get('plan_type', 'Unknown') or 'Unknown').upper()
        plan = truncate_display_text(plan, plan_width)
        plan_cell = pad_display(plan, plan_width)
        if 'TEAM' in plan:
            plan_display = f"{Colors.CYAN}{plan_cell}{Colors.ENDC}"
        elif 'PLUS' in plan:
            plan_display = f"{Colors.BLUE}{plan_cell}{Colors.ENDC}"
        else:
            plan_display = f"{Colors.DIM}{plan_cell}{Colors.ENDC}"

        # 使用量 - 计算剩余百分比
        hourly_percent = acc.get('hourly_percent', 0)
        weekly_percent = acc.get('weekly_percent', 0)
        hourly_remaining = 100 - hourly_percent if isinstance(hourly_percent, (int, float)) else 0
        weekly_remaining = 100 - weekly_percent if isinstance(weekly_percent, (int, float)) else 0

        # 根据剩余百分比选择颜色
        def get_color(pct):
            if pct >= 50:
                return Colors.GREEN
            elif pct >= 20:
                return Colors.YELLOW
            else:
                return Colors.RED

        hourly_reset = format_reset_time_compact(acc.get('reset_at_hourly', 0))
        weekly_reset = format_reset_time_compact(acc.get('reset_at_weekly', 0))
        hourly_str = f"剩余{hourly_remaining}%({hourly_reset})"
        weekly_str = f"剩余{weekly_remaining}%({weekly_reset})"

        # 带颜色的使用量显示
        hourly_display = f"{get_color(hourly_remaining)}{pad_display(hourly_str, hourly_width)}{Colors.ENDC}"
        weekly_display = f"{get_color(weekly_remaining)}{pad_display(weekly_str, weekly_width)}{Colors.ENDC}"

        index_cell = pad_display(str(i), 2)
        print(f"  {index_cell} {email_cell} {space_cell} {plan_display} {hourly_display} {weekly_display}")

    if highlight_current_first and current_rows:
        for i, acc in enumerate(current_rows, 1):
            render_row(i, acc)
        if other_rows:
            print()
        start_index = len(current_rows) + 1
        for offset, acc in enumerate(other_rows, start_index):
            render_row(offset, acc)
    else:
        for i, acc in enumerate(accounts, 1):
            render_row(i, acc)

    print()

def format_reset_time(reset_at_ts: int) -> str:
    """将 Unix 时间戳格式化为可读的重置时间"""
    if not reset_at_ts:
        return 'N/A'
    try:
        # 转换为本地时间
        dt = datetime.fromtimestamp(reset_at_ts)
        now = datetime.now()

        # 计算时间差
        delta = dt - now
        total_seconds = int(delta.total_seconds())

        if total_seconds <= 0:
            return "即将重置"

        # 格式化具体时间点
        time_str = dt.strftime('%H:%M')

        # 判断是今天还是其他日期
        if dt.date() == now.date():
            date_str = "今天"
        elif dt.date() == (now + timedelta(days=1)).date():
            date_str = "明天"
        else:
            date_str = dt.strftime('%m/%d')

        # 计算剩余时间
        if total_seconds >= 86400:  # 超过1天
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            remaining = f"{days}d{hours}h"
        elif total_seconds >= 3600:  # 超过1小时
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            remaining = f"{hours}h{minutes}m"
        else:
            minutes = total_seconds // 60
            remaining = f"{minutes}m"

        return f"{date_str} {time_str} ({remaining})"
    except:
        return 'N/A'

def format_reset_time_compact(reset_at_ts: int) -> str:
    """将 Unix 时间戳格式化为列表紧凑展示"""
    if not reset_at_ts:
        return '?'
    try:
        dt = datetime.fromtimestamp(reset_at_ts)
        now = datetime.now()
        if dt <= now:
            return '即将'

        if dt.date() == now.date():
            return dt.strftime('%H:%M')
        if dt.date() == (now + timedelta(days=1)).date():
            return f"明{dt.strftime('%H:%M')}"
        return dt.strftime('%m/%d %H:%M')
    except Exception:
        return '?'

def refresh_account_usage(email: str, access_token: str, account_id: str) -> Optional[dict]:
    """刷新单个账号的使用量（静默版本）"""
    payload, _, _ = request_usage_payload(access_token, account_id)
    if not payload:
        return None
    usage_data = build_usage_data(payload)
    if not usage_data:
        return None
    save_usage_cache(email, usage_data, account_id)
    return usage_data

def collect_account_entries() -> List[dict]:
    """收集当前账号和已存档账号的显示条目"""
    entries = []

    current_path = get_auth_file()
    current_auth = load_auth_data_from_path(current_path)
    if current_auth:
        current_info = get_account_info(current_auth, str(current_path))
        if current_info:
            entries.append({
                'kind': 'current',
                'path': current_path,
                'identity': current_info.get('record_key') or str(current_path),
                'info': current_info,
            })

    accounts_dir = get_accounts_dir()
    if not accounts_dir.exists():
        return entries

    for auth_file in sorted(accounts_dir.glob('auth_*.json')):
        auth_data = load_auth_data_from_path(auth_file)
        if not auth_data:
            continue
        info = get_account_info(auth_data, str(auth_file))
        if not info:
            continue
        entries.append({
            'kind': 'saved',
            'path': auth_file,
            'saved_name': auth_file.stem.replace('auth_', ''),
            'identity': info.get('record_key') or str(auth_file),
            'info': info,
        })

    return entries

def is_current_account_saved(current_record_key: str) -> bool:
    """检查当前账号是否已经存在于存档中"""
    if not current_record_key:
        return False

    accounts_dir = get_accounts_dir()
    if not accounts_dir.exists():
        return False

    for auth_file in sorted(accounts_dir.glob('auth_*.json')):
        auth_data = load_auth_data_from_path(auth_file)
        if not auth_data:
            continue
        info = get_account_info(auth_data, str(auth_file))
        if info and info.get('record_key') == current_record_key:
            return True
    return False

def ensure_current_account_saved() -> bool:
    """自动存档当前未存档账号"""
    auth_data = load_current_auth()
    if not auth_data:
        return False

    info = get_account_info(auth_data, str(get_auth_file()))
    if not info:
        return False

    record_key = info.get('record_key', '')
    if is_current_account_saved(record_key):
        return True

    save_name = info.get('email', 'account')
    return save_current_auth(save_name)

def clone_display_info(info: dict, entry: dict) -> dict:
    """克隆用于展示的账号信息"""
    display = dict(info)
    display['file_path'] = str(entry['path'])
    if entry.get('saved_name'):
        display['saved_name'] = entry['saved_name']
    return display

def print_refresh_progress(current: int, total: int, width: int = 24):
    """打印刷新进度条"""
    if total <= 0:
        return
    filled = int(width * current / total)
    bar = f"{Colors.GREEN}{'#' * filled}{Colors.DIM}{'-' * (width - filled)}{Colors.ENDC}"
    sys.stdout.write(f"\r  刷新进度: [{bar}] {current}/{total}")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()

def refresh_view_job(job: Dict[str, Any]) -> dict:
    """执行单个账号的实时刷新任务"""
    primary_path = Path(job['primary_path'])
    seed_info = dict(job['seed_info'])

    refreshed_info = refresh_usage_for_auth_path(primary_path)
    if not refreshed_info:
        refreshed_info = seed_info
        refreshed_info['refresh_status'] = 'cached'
        refreshed_info['refresh_status_text'] = '缓存'

    refreshed_auth = load_auth_data_from_path(primary_path)
    if refreshed_auth and len(job['paths']) > 1:
        for extra_path in job['paths']:
            extra_path = Path(extra_path)
            if extra_path == primary_path:
                continue
            mirror_auth_tokens_to_path(extra_path, refreshed_auth)

    return refreshed_info

def build_refresh_jobs(entries: List[dict]) -> Dict[str, Dict[str, Any]]:
    """根据账号条目构建去重后的刷新任务"""
    refresh_jobs: Dict[str, Dict[str, Any]] = {}

    for entry in entries:
        identity = entry['identity']
        job = refresh_jobs.get(identity)
        if not job:
            refresh_jobs[identity] = {
                'primary_path': entry['path'],
                'paths': [entry['path']],
                'has_current': entry['kind'] == 'current',
                'seed_info': entry['info'],
            }
            continue

        job['paths'].append(entry['path'])
        if entry['kind'] == 'current' and not job['has_current']:
            job['primary_path'] = entry['path']
            job['has_current'] = True

    return refresh_jobs

def refresh_jobs_live(
    refresh_jobs: Dict[str, Dict[str, Any]],
    show_progress: bool = False,
) -> Dict[str, dict]:
    """并发刷新所有账号的最新在线数据"""
    results: Dict[str, dict] = {}
    job_items = list(refresh_jobs.items())
    if not job_items:
        return results

    if show_progress:
        print()

    max_workers = min(len(job_items), MAX_REFRESH_WORKERS)
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(refresh_view_job, job): (identity, job)
            for identity, job in job_items
        }

        for future in as_completed(future_map):
            identity, job = future_map[future]
            try:
                results[identity] = future.result()
            except Exception:
                fallback = dict(job['seed_info'])
                fallback['refresh_status'] = 'cached'
                fallback['refresh_status_text'] = '缓存'
                results[identity] = fallback

            completed += 1
            if show_progress:
                print_refresh_progress(completed, len(job_items))

    return results

def build_view_all_rows(
    refresh_jobs: Dict[str, Dict[str, Any]],
    results: Dict[str, dict],
) -> List[dict]:
    """构建查看余量页面的统一账号行"""
    rows = []
    current_auth_path = str(get_auth_file())

    for identity, job in refresh_jobs.items():
        base_info = results.get(identity) or job['seed_info']
        all_paths = [str(path) for path in job['paths']]
        saved_paths = [path for path in all_paths if path != current_auth_path]

        row = dict(base_info)
        row['identity'] = identity
        row['is_current'] = job['has_current']
        row['is_saved'] = bool(saved_paths)
        row['switch_path'] = saved_paths[0] if saved_paths else None
        rows.append(row)

    return rows

def load_live_account_rows(show_progress: bool = False) -> List[dict]:
    """加载并实时刷新账号列表"""
    ensure_current_account_saved()
    entries = collect_account_entries()
    refresh_jobs = build_refresh_jobs(entries)
    results = refresh_jobs_live(refresh_jobs, show_progress=show_progress)
    return build_view_all_rows(refresh_jobs, results)

def get_remaining_percent(acc: dict, window: str) -> int:
    """获取指定窗口的剩余百分比"""
    key = 'hourly_percent' if window == 'hourly' else 'weekly_percent'
    used_percent = acc.get(key, 0)
    if not isinstance(used_percent, (int, float)):
        return -1
    return max(0, 100 - int(used_percent))

def get_remaining_count(acc: dict, window: str) -> int:
    """获取指定窗口的剩余数量"""
    key = 'hourly_remaining' if window == 'hourly' else 'weekly_remaining'
    value = acc.get(key, '')
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1

def sort_accounts_for_agent(rows: List[dict]) -> List[dict]:
    """按 5 小时剩余数量、每周剩余数量排序账号"""
    return sorted(
        rows,
        key=lambda acc: (
            -get_remaining_count(acc, 'hourly'),
            -get_remaining_count(acc, 'weekly'),
            str(acc.get('email', '')),
        ),
    )

def sort_accounts_for_live_view(rows: List[dict]) -> List[dict]:
    """查看余量页排序：当前账号置顶，其他账号按剩余数量排序"""
    current_rows = [row for row in rows if row.get('is_current')]
    other_rows = [row for row in rows if not row.get('is_current')]
    return current_rows + sort_accounts_for_agent(other_rows)

def is_account_unavailable(row: dict) -> bool:
    """Treat reauth/cached-without-usage rows as unavailable snapshots."""
    if row.get('is_current'):
        return False

    refresh_status = str(row.get('refresh_status', '') or '').lower()
    if refresh_status == 'reauth':
        return True

    has_usage_window = bool(row.get('reset_at_hourly') or row.get('reset_at_weekly'))
    if refresh_status in {'cached', 'unknown'} and not has_usage_window:
        return True
    return False

def filter_rows_for_view(rows: List[dict], show_unavailable: bool) -> List[dict]:
    """Hide unavailable saved snapshots unless explicitly requested."""
    if show_unavailable:
        return rows
    return [row for row in rows if not is_account_unavailable(row)]

def delete_saved_account_file(file_path: str) -> bool:
    """Delete a saved auth snapshot only when it lives in the accounts directory."""
    if not file_path:
        return False
    try:
        target = Path(file_path).resolve()
        accounts_dir = get_accounts_dir().resolve()
        target.relative_to(accounts_dir)
    except Exception:
        return False

    if not target.exists() or not target.is_file():
        return False

    try:
        target.unlink()
        return True
    except Exception:
        return False

def cleanup_unavailable_rows(rows: List[dict]) -> int:
    """Remove unavailable saved snapshots from disk."""
    deleted = 0
    visited = set()
    for row in rows:
        switch_path = str(row.get('switch_path') or '')
        if not switch_path or switch_path in visited:
            continue
        if not is_account_unavailable(row):
            continue
        if delete_saved_account_file(switch_path):
            deleted += 1
            visited.add(switch_path)
    return deleted

def serialize_account(acc: dict, rank: Optional[int] = None) -> dict:
    """将账号信息序列化为 CLI/JSON 输出"""
    data = {
        'rank': rank,
        'email': acc.get('email', ''),
        'plan_type': str(acc.get('plan_type', '') or '').upper(),
        'is_current': bool(acc.get('is_current')),
        'is_saved': bool(acc.get('is_saved')),
        'identity': acc.get('identity', ''),
        'switch_path': acc.get('switch_path'),
        'hourly_remaining_pct': get_remaining_percent(acc, 'hourly'),
        'weekly_remaining_pct': get_remaining_percent(acc, 'weekly'),
        'hourly_reset_at': acc.get('reset_at_hourly', 0),
        'weekly_reset_at': acc.get('reset_at_weekly', 0),
        'hourly_reset': format_reset_time_compact(acc.get('reset_at_hourly', 0)),
        'weekly_reset': format_reset_time_compact(acc.get('reset_at_weekly', 0)),
    }
    return data

def print_ranked_accounts(rows: List[dict], title: str = "可用账号"):
    """输出按剩余量排序后的账号列表"""
    if not rows:
        print("没有可用账号")
        return

    print()
    print(f"{Colors.BOLD}{title}{Colors.ENDC}")
    print_accounts_table(rows, title="")
    print(f"{Colors.DIM}共 {len(rows)} 个账号{Colors.ENDC}")

def resolve_account_selector(rows: List[dict], selector: str) -> Optional[dict]:
    """根据 index/email/identity/best 解析账号选择器"""
    ranked = sort_accounts_for_agent(rows)
    normalized = selector.strip()
    if not normalized:
        return None

    if normalized.lower() == 'best':
        return ranked[0] if ranked else None

    if normalized.isdigit():
        idx = int(normalized) - 1
        if 0 <= idx < len(ranked):
            return ranked[idx]
        return None

    lowered = normalized.lower()
    for row in ranked:
        if row.get('email', '').lower() == lowered:
            return row
        if row.get('identity', '') == normalized:
            return row
    return None

def print_view_all_actions(rows: List[dict], show_unavailable: bool, hidden_count: int):
    """打印查看余量页面底部操作"""
    print(f"{Colors.BOLD}  操作面板{Colors.ENDC}")
    print(f"{Colors.DIM}  {'─' * 40}{Colors.ENDC}")
    print(f"  {Colors.CYAN}[编号]{Colors.ENDC} 切换账号")
    print(f"  {Colors.CYAN}[d 编号]{Colors.ENDC} 删除指定快照")
    print(f"  {Colors.CYAN}[c]{Colors.ENDC} 清理失效/掉线快照")
    toggle_label = '隐藏失效账号' if show_unavailable else '显示失效账号'
    print(f"  {Colors.CYAN}[a]{Colors.ENDC} {toggle_label}")
    if hidden_count > 0 and not show_unavailable:
        print(f"  {Colors.DIM}当前已隐藏 {hidden_count} 个失效快照{Colors.ENDC}")
    print(f"  {Colors.CYAN}[0]{Colors.ENDC} 退出工具")
    print(f"  {Colors.DIM}[Enter]{Colors.ENDC} 刷新当前页面")
    print()

def view_all_accounts():
    """查看所有账号（自动刷新使用量）"""
    show_unavailable = False
    while True:
        clear_screen()
        print_header()
        print(f"\n{Colors.CYAN}>>> 查看所有账号余量{Colors.ENDC}")
        all_rows = sort_accounts_for_live_view(load_live_account_rows(show_progress=True))
        rows = filter_rows_for_view(all_rows, show_unavailable)
        hidden_count = max(0, len(all_rows) - len(rows))
        clear_screen()
        print_header()
        print(f"\n{Colors.CYAN}>>> 查看所有账号余量{Colors.ENDC}")
        if rows:
            print_accounts_table(rows, "账号列表", highlight_current_first=True)
        else:
            print(f"\n{Colors.YELLOW}  当前未登录任何账号，且没有已存档账号{Colors.ENDC}")

        summary = f"  共 {len(rows)} 个账号"
        if hidden_count > 0 and not show_unavailable:
            summary += f"（已隐藏 {hidden_count} 个失效快照）"
        print(f"{Colors.DIM}{summary}{Colors.ENDC}")
        print()
        print_view_all_actions(rows, show_unavailable, hidden_count)

        try:
            choice = input("  请选择: ").strip()
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}  已取消{Colors.ENDC}")
            return

        if choice == '':
            continue
        if choice == '0':
            return

        lowered = choice.lower()
        if lowered == 'a':
            show_unavailable = not show_unavailable
            continue

        if lowered == 'c':
            deleted = cleanup_unavailable_rows(all_rows)
            if deleted:
                print(f"\n{Colors.GREEN}  ✓ 已清理 {deleted} 个失效快照{Colors.ENDC}")
            else:
                print(f"\n{Colors.YELLOW}  没有可清理的失效快照{Colors.ENDC}")
            input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
            continue

        if lowered.startswith('d'):
            parts = choice.split(maxsplit=1)
            selector = parts[1].strip() if len(parts) > 1 else ''
            if not selector.isdigit():
                print(f"\n{Colors.RED}  删除请使用 d 编号，例如 d 3{Colors.ENDC}")
                input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
                continue

            idx = int(selector) - 1
            if idx < 0 or idx >= len(rows):
                print(f"\n{Colors.RED}  无效的编号{Colors.ENDC}")
                input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
                continue

            row = rows[idx]
            if row.get('is_current'):
                print(f"\n{Colors.YELLOW}  当前登录账号不能直接删除{Colors.ENDC}")
                input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
                continue

            switch_path = row.get('switch_path')
            if not switch_path or not delete_saved_account_file(switch_path):
                print(f"\n{Colors.RED}  删除失败：未找到可删除的快照文件{Colors.ENDC}")
                input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
                continue

            print(f"\n{Colors.GREEN}  ✓ 已删除快照: {row.get('email', 'Unknown')}{Colors.ENDC}")
            input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
            continue

        try:
            idx = int(choice) - 1
        except ValueError:
            print(f"\n{Colors.RED}  请输入编号、d 编号、a、c、0 或直接回车{Colors.ENDC}")
            input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
            continue

        if idx < 0 or idx >= len(rows):
            print(f"\n{Colors.RED}  无效的编号{Colors.ENDC}")
            input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
            continue

        row = rows[idx]
        if row.get('is_current'):
            print(f"\n{Colors.YELLOW}  该账号已经是当前登录账号{Colors.ENDC}")
            input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
            continue

        switch_path = row.get('switch_path')
        if not switch_path:
            print(f"\n{Colors.RED}  该账号尚未存档，无法切换{Colors.ENDC}")
            input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
            continue

        print(f"\n{Colors.CYAN}  正在切换到: {row.get('email', 'Unknown')}{Colors.ENDC}")
        if switch_to_account(switch_path):
            print(f"{Colors.GREEN}  ✓ 切换成功！{Colors.ENDC}")
            finish_switch_with_restart()
            time.sleep(1.0)
            continue
        else:
            print(f"{Colors.RED}  ✗ 切换失败{Colors.ENDC}")
        input(f"{Colors.DIM}按回车键继续...{Colors.ENDC}")
        continue

def switch_account():
    """切换账号"""
    clear_screen()
    print_header()
    print(f"\n{Colors.CYAN}>>> 切换账号{Colors.ENDC}")

    print_current_account()

    saved = list_saved_accounts()
    if not saved:
        print(f"{Colors.YELLOW}没有已存档的账号，请先使用功能(3)存档当前账号{Colors.ENDC}")
        return

    print_accounts_table(saved, "选择要切换的账号")

    print(f"  {Colors.DIM}输入编号切换，输入 0 取消{Colors.ENDC}")
    print()

    try:
        choice = input(f"  请选择: ").strip()
        if choice == '0' or choice == '':
            return

        idx = int(choice) - 1
        if 0 <= idx < len(saved):
            account = saved[idx]
            print()
            print(f"{Colors.CYAN}  正在切换到: {account['email']}{Colors.ENDC}")

            if switch_to_account(account['file_path']):
                print(f"{Colors.GREEN}  ✓ 切换成功！{Colors.ENDC}")
                finish_switch_with_restart()
                time.sleep(1.0)
                return
            else:
                print(f"{Colors.RED}  ✗ 切换失败{Colors.ENDC}")
        else:
            print(f"{Colors.RED}  无效的选择{Colors.ENDC}")
    except ValueError:
        print(f"{Colors.RED}  请输入有效的数字{Colors.ENDC}")
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}  已取消{Colors.ENDC}")

def save_account():
    """存档当前账号"""
    clear_screen()
    print_header()
    print(f"\n{Colors.CYAN}>>> 存档当前登录账号{Colors.ENDC}")

    info = print_current_account()
    if not info:
        return

    print(f"  {Colors.DIM}输入存档名称（直接回车使用完整邮箱）{Colors.ENDC}")
    print()

    try:
        name = input(f"  存档名称: ").strip()
        if not name:
            name = info.get('email', 'account')

        print()
        print(f"{Colors.CYAN}  正在存档: {name}{Colors.ENDC}")

        if save_current_auth(name):
            print(f"{Colors.GREEN}  ✓ 存档成功！{Colors.ENDC}")
            print(f"{Colors.DIM}  保存位置: {get_accounts_dir()}{Colors.ENDC}")
        else:
            print(f"{Colors.RED}  ✗ 存档失败{Colors.ENDC}")
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}  已取消{Colors.ENDC}")

def refresh_usage():
    """刷新使用量"""
    clear_screen()
    print_header()
    print(f"\n{Colors.CYAN}>>> 刷新使用量{Colors.ENDC}")

    auth_path = get_auth_file()
    auth_data = load_current_auth()
    if not auth_data:
        print(f"{Colors.YELLOW}当前未登录任何账号{Colors.ENDC}")
        return

    info = get_account_info(auth_data, str(auth_path))
    if not info:
        print(f"{Colors.RED}无法解析当前账号信息{Colors.ENDC}")
        return

    email = info.get('email', '')

    print(f"\n  账号: {email}")
    print()

    refreshed_info = refresh_usage_for_auth_path(auth_path)
    if refreshed_info:
        info = refreshed_info

    usage_cache = load_usage_cache(
        info.get('email', ''),
        info.get('account_id', ''),
        info.get('record_key', ''),
    )

    if usage_cache:
        plan_type = usage_cache.get('plan_type', info.get('plan_type', 'unknown'))
        hourly_percent = usage_cache.get('hourly_percent', 0)
        weekly_percent = usage_cache.get('weekly_percent', 0)
        hourly_remaining = 100 - hourly_percent if hourly_percent else 0
        weekly_remaining = 100 - weekly_percent if weekly_percent else 0

        # 根据剩余百分比选择颜色
        def get_remaining_color(pct):
            if pct >= 50:
                return Colors.GREEN
            elif pct >= 20:
                return Colors.YELLOW
            else:
                return Colors.RED

        print()
        print(f"  {Colors.BOLD}使用量信息:{Colors.ENDC}")
        print(f"  {Colors.DIM}{'─' * 50}{Colors.ENDC}")
        print(f"  计划类型:   {Colors.CYAN}{plan_type.upper()}{Colors.ENDC}")
        print(f"  刷新状态:   {info.get('refresh_status_text', '未刷新')}")
        print()
        print(f"  5小时限额:  {get_remaining_color(hourly_remaining)}剩余 {hourly_remaining}%{Colors.ENDC}  (重置: {usage_cache.get('next_reset', 'N/A')})")
        print(f"  每周限额:   {get_remaining_color(weekly_remaining)}剩余 {weekly_remaining}%{Colors.ENDC}  (重置: {usage_cache.get('next_reset_weekly', 'N/A')})")

def build_arg_parser() -> argparse.ArgumentParser:
    """构建非交互 CLI 参数解析器"""
    parser = argparse.ArgumentParser(
        prog='codex-switcher',
        description='Codex 账号切换与余量查看工具',
    )
    parser.add_argument('--list', action='store_true', help='实时列出账号并按剩余量排序')
    parser.add_argument('--json', action='store_true', help='以 JSON 输出结果')
    parser.add_argument('--best', action='store_true', help='输出当前最佳账号')
    parser.add_argument('--switch', metavar='SELECTOR', help='按序号、邮箱或 best 切换账号')
    parser.add_argument(
        '--save-current',
        nargs='?',
        const='__AUTO__',
        metavar='NAME',
        help='非交互存档当前账号，可选指定名称',
    )
    parser.add_argument('--refresh', action='store_true', help='实时刷新当前账号使用量后退出')
    return parser

def run_list_command(json_output: bool) -> int:
    """执行账号列表命令"""
    rows = sort_accounts_for_agent(load_live_account_rows(show_progress=False))
    if json_output:
        print(json.dumps([serialize_account(row, i) for i, row in enumerate(rows, 1)], ensure_ascii=False, indent=2))
        return 0

    print_accounts_table(rows, "账号列表（按 5 小时 / 每周余量排序）")
    return 0

def run_best_command(json_output: bool) -> int:
    """执行最佳账号命令"""
    rows = sort_accounts_for_agent(load_live_account_rows(show_progress=False))
    best = rows[0] if rows else None
    if json_output:
        print(json.dumps(serialize_account(best, 1) if best else {}, ensure_ascii=False, indent=2))
        return 0

    if not best:
        print("没有可用账号")
        return 1
    print_accounts_table([best], "最佳账号")
    return 0

def run_switch_command(selector: str, json_output: bool) -> int:
    """执行非交互切换命令"""
    rows = sort_accounts_for_agent(load_live_account_rows(show_progress=False))
    target = resolve_account_selector(rows, selector)
    if not target:
        message = {'ok': False, 'error': f'未找到账号选择器: {selector}'}
        print(json.dumps(message, ensure_ascii=False, indent=2) if json_output else message['error'])
        return 1

    if target.get('is_current'):
        payload = {'ok': True, 'message': '目标账号已经是当前账号', 'account': serialize_account(target, 1)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else payload['message'])
        return 0

    switch_path = target.get('switch_path')
    if not switch_path:
        payload = {'ok': False, 'error': '目标账号尚未存档，无法切换'}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else payload['error'])
        return 1

    switched = switch_to_account(switch_path)
    if switched:
        restart_info = finish_switch_with_restart(quiet=json_output)
        payload = {
            'ok': True,
            'message': '切换成功',
            'account': serialize_account(target, 1),
            'restart': restart_info,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else f"切换成功: {target.get('email', '')}")
        return 0

    payload = {'ok': False, 'error': '切换失败'}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else payload['error'])
    return 1

def run_save_current_command(name_arg: str, json_output: bool) -> int:
    """执行非交互存档当前账号命令"""
    auth_data = load_current_auth()
    info = get_account_info(auth_data, str(get_auth_file())) if auth_data else None
    if not info:
        payload = {'ok': False, 'error': '当前未登录任何账号'}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else payload['error'])
        return 1

    save_name = info.get('email', 'account') if name_arg == '__AUTO__' else name_arg
    save_name = save_name or info.get('email', 'account')
    saved = save_current_auth(save_name)
    payload = {'ok': saved, 'name': save_name, 'email': info.get('email', '')}
    if not saved:
        payload['error'] = '存档失败'
    print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else ('存档成功' if saved else '存档失败'))
    return 0 if saved else 1

def run_refresh_command(json_output: bool) -> int:
    """执行非交互刷新当前账号命令"""
    auth_path = get_auth_file()
    info = refresh_usage_for_auth_path(auth_path)
    if not info:
        payload = {'ok': False, 'error': '当前未登录任何账号或无法刷新'}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else payload['error'])
        return 1

    usage_cache = load_usage_cache(info.get('email', ''), info.get('account_id', ''), info.get('record_key', ''))
    payload = {'ok': True, 'account': serialize_account(info, 1), 'usage': usage_cache or {}}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if json_output else f"刷新完成: {info.get('email', '')}")
    return 0

def run_noninteractive(args: argparse.Namespace) -> int:
    """执行非交互 CLI 命令"""
    if args.save_current is not None:
        return run_save_current_command(args.save_current, args.json)
    if args.switch:
        return run_switch_command(args.switch, args.json)
    if args.best:
        return run_best_command(args.json)
    if args.refresh:
        return run_refresh_command(args.json)
    if args.list or args.json:
        return run_list_command(args.json)
    return 0

def main():
    """主函数"""
    # 确保目录存在
    get_accounts_dir().mkdir(parents=True, exist_ok=True)
    get_usage_cache_dir().mkdir(parents=True, exist_ok=True)
    parser = build_arg_parser()
    args = parser.parse_args()

    if any([args.list, args.json, args.best, args.switch, args.save_current is not None, args.refresh]):
        raise SystemExit(run_noninteractive(args))

    try:
        view_all_accounts()
    except KeyboardInterrupt:
        pass

    clear_screen()
    print(f"{Colors.GREEN}再见！{Colors.ENDC}")

if __name__ == '__main__':
    main()
