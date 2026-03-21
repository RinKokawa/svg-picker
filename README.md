# svg-picker

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

- **Native GUI** — PySide6 dark-themed window, no browser required
- **Iconify API** — Access to 150+ icon sets, 500,000+ icons
- **stdout output** — SVG code flows directly into the AI's context
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
svg-picker <keyword>
```

Example:

```bash
svg-picker home
```

1. Window opens with matching icons
2. Click to select one or more
3. Press **Confirm** — SVG source code is printed to stdout, window closes
4. The AI agent receives the SVG code and uses it in code

---

## For AI Agents

### As a Claude Code Skill

Place this file as `~/.claude/skills/svg-picker.md`:

```markdown
# svg-picker

Pick SVG icons via keyword search with human visual selection.

Usage: svg-picker <keyword>

The human selects icons from the window. SVG source code is output to stdout.
```

### Programmatic Usage

```python
import subprocess

result = subprocess.run(["svg-picker", "home"], capture_output=True, text=True)
svg_code = result.stdout
# svg_code now contains the raw SVG source
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
