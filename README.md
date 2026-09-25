# svg-picker

[![PyPI version](https://img.shields.io/pypi/v/svg-picker)](https://pypi.org/project/svg-picker/)
[![Python versions](https://img.shields.io/pypi/pyversions/svg-picker)](https://pypi.org/project/svg-picker/)
[![License](https://img.shields.io/pypi/l/svg-picker)](https://github.com/RinKokawa/svg-picker/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/svg-picker)](https://pypistats.org/packages/svg-picker)

**A Human-in-the-Loop Icon Selector for AI Agents**

> Inspired by [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924) (ICSE SEIP 2025)

---

## What Is This?

svg-picker is a lightweight tool that gives AI coding agents the ability to **ask a human to visually select an icon**, then returns the SVG source code directly to the agent via stdout.

Instead of guessing icon names or embedding random SVG strings, the AI can now say:

> "I need a home icon — please select one from the options"

A native dark-themed window opens. The human picks. The AI gets clean SVG code.

**The human provides visual judgment. The AI handles everything else.**

---

## Background: Why "Human-in-the-Loop"?

The paper [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924) (Takerngsaksiri et al., ICSE SEIP 2025) demonstrates a critical insight:

> Existing LLM-based coding agents rarely incorporate human feedback at intermediate stages. When humans can intervene during plan generation and code writing — not just review final output — development time and effort decrease significantly.

HULA was deployed at **Atlassian JIRA** and evaluated by real engineers. The results confirm what many suspected: **fully autonomous AI agents produce better outcomes when humans stay in the loop**.

svg-picker applies this principle to a specific, narrow task: **icon selection**. It is a minimal, production-ready implementation of human-in-the-loop tooling for AI agents — without the complexity of a full framework.

---

## How It Works

```
User/CI:  svg-picker <keyword>
            │
            ▼
    ┌─────────────────┐
    │  Search Iconify  │   (Background thread)
    │  Download SVGs    │
    └────────┬────────┘
               │
               ▼
    ┌─────────────────────┐
    │   GUI Window        │   ← Human picks icon(s)
    │   Dark theme        │
    │   Click to select   │
    └────────┬───────────┘
               │
               ▼
         SVG code to stdout  →  AI agent consumes it
```

The human acts as a **visual judge** — the AI remains in full control of the workflow.

---

## Features

- **Native GUI** — PySide6 window, no browser required
- **Themable** — `cream` / `sky` / `dark` backgrounds via `--theme`
- **Pagination** — 10 icons per page, flip with `‹` / `›` buttons or `←` / `→` keys; selections persist across pages
- **Iconify API** — Access to 150+ icon sets, 500,000+ icons
- **stdout output** — SVG code flows directly into the AI's context
- **Cancellation signal** — closing the window writes `[svg-picker] cancelled: ...` to stderr so callers can distinguish user cancel from program crash
- **One-step install** — pip install, single command
- **Zero config** — No API keys, no servers, no infrastructure

---

## Install

```bash
pip install svg-picker
```

Or for development:

```bash
pip install -e .
```

---

## Usage

```bash
svg-picker <keyword> [--theme cream|sky|dark]
```

### Options

| Flag | Description |
|---|---|
| `-t`, `--theme <name>` | Background theme. Choices: `cream` (default), `sky`, `dark` |

### Examples

```bash
svg-picker home                  # default cream theme
svg-picker home --theme sky      # sky blue background
svg-picker arrow -t dark         # dark theme, short flag
```

### Default theme via `.env`

To set a project-wide default without typing `--theme` every time, edit `.env` in the directory you run `svg-picker` from. On first launch, `svg-picker` creates an empty `.env` for you if one doesn't exist — just add a line like:

```ini
# .env
SVG_PICKER_THEME=sky
```

Resolution order: **CLI `--theme` → `.env` `SVG_PICKER_THEME` → `cream`**. An invalid value in `.env` prints a warning to stderr and falls back to the built-in default.

### Steps

1. Window opens with the first page of 10 matching icons
2. Click to select one or more; click again to deselect
3. Flip pages with `‹` / `›` buttons or `←` / `→` keys — selections persist across pages
4. Press **Confirm** — SVG source code is printed to stdout, window closes
5. Close the window (X) to cancel — a `[svg-picker] cancelled: ...` line is written to stderr

---

## For AI Agents

### As a Claude Code Skill

Place this file as `~/.claude/skills/svg-picker.md`:

```markdown
# svg-picker

Pick SVG icons via keyword search with human visual selection.

Usage: svg-picker <keyword> [--theme cream|sky|dark]

The human selects icons from the window. SVG source code is output to stdout.
If the window is closed without confirming, a "[svg-picker] cancelled: ..."
line is written to stderr — read stderr to distinguish cancel from crash.
```

### Programmatic Usage

```python
import subprocess

result = subprocess.run(
    ["svg-picker", "home"],
    capture_output=True, text=True,
)

if result.returncode != 0:
    # 程序异常退出 —— stderr 会有 Python traceback
    raise RuntimeError(f"svg-picker crashed: {result.stderr}")

if "[svg-picker] cancelled" in result.stderr:
    # 用户主动关闭窗口,没点 Confirm
    if "selected but not confirmed" in result.stderr:
        # 选了但没用上 —— 尊重取消意图,不要 fallback
        print("User cancelled with selections discarded")
    else:
        print("User cancelled without selection")
else:
    # 正常完成 —— result.stdout 是 SVG 源码
    svg_code = result.stdout
    # 每段格式:<!-- iconify_id -->\n<svg>...</svg>
```

---

## Comparison

| | svg-picker | HULA (Atlassian) |
|---|---|---|
| Domain | Icon selection | Full software dev |
| Scope | Minimal, single-task | Full agent framework |
| Human role | Visual judge | Plan + code reviewer |
| Deployment | pip install | Jira plugin |
| Target | AI agents | Human engineers |

Both share the same core principle: **human judgment improves AI output**.

---

## Related Work

- [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924) — ICSE SEIP 2025
- [acte](https://github.com/j66n/acte) — Framework for GUI-like Agent Tools
- [OpenUI](https://github.com/thesysdev/openui) — Open Standard for Generative UI

---

## License

MIT
