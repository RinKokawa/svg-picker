# svg-picker

**面向 AI Agent 的人类辅助图标选择工具**

> 受论文 [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924) (ICSE SEIP 2025) 启发

---

## 这是什么？

svg-picker 是一个轻量级工具，让 AI 编程 Agent 能够**请人类视觉化地选择一个图标**，然后通过 stdout 将 SVG 源码直接返回给 Agent。

AI 不再需要猜测图标名称或嵌入随机的 SVG 字符串，而是可以说：

> "我需要一个 home 图标——请从选项中选一个"

一个原生暗色主题窗口弹出，人类选择后，AI 获得干净的 SVG 代码。

**人类提供视觉判断，AI 掌控其余工作流。**

---

## 背景：为什么需要"人在回路"？

论文 [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924)（Takerngsaksiri 等，ICSE SEIP 2025）验证了一个关键洞察：

> 现有的 LLM 编程 Agent 很少在中间阶段引入人类反馈。当人类可以在规划生成和代码编写过程中介入——而非仅仅审查最终输出——开发时间和工作量会显著减少。

HULA 已部署于 **Atlassian JIRA** 并由真实工程师评估。结果证实了一个普遍认知：**在人类保持参与的情况下，完全自主的 AI Agent 能产生更好的结果。**

svg-picker 将这一原则应用于一个具体、狭窄的任务：**图标选择**。它是一个最小化、生产就绪的"人类在回路"工具实现——无需完整框架的复杂度。

---

## 工作原理

```
用户/CI:  svg-picker <关键词>
            │
            ▼
    ┌─────────────────┐
    │  搜索 Iconify    │   (后台线程)
    │  下载 SVG 文件    │
    └────────┬────────┘
               │
               ▼
    ┌─────────────────────┐
    │   GUI 窗口           │   ← 人类选择图标
    │   暗色主题           │
    │   点击选中           │
    └────────┬───────────┘
               │
               ▼
         SVG 代码输出到 stdout  →  AI Agent 消费
```

人类扮演**视觉裁判**的角色——AI 始终掌控整个工作流。

---

## 功能特点

- **原生 GUI** — PySide6 窗口，无需浏览器
- **可换主题** — `cream` / `sky` / `dark` 三种背景(`--theme` 切换)
- **分页浏览** — 每页 10 个图标，按 `‹` / `›` 按钮或 `←` / `→` 键翻页；选中状态跨页保留
- **Iconify API** — 接入 150+ 图标集、50 万+ 图标
- **stdout 输出** — SVG 代码直接流入 AI 上下文
- **取消信号** — 关闭窗口时往 stderr 写 `[svg-picker] cancelled: ...`，调用方可区分"用户取消"和"程序崩溃"
- **一步安装** — pip install，一条命令
- **零配置** — 无需 API Key、无服务器、无基础设施

---

## 安装

```bash
pip install svg-picker
```

或开发模式：

```bash
pip install -e .
```

---

## 使用方法

```bash
svg-picker <关键词> [--theme cream|sky|dark]
```

### 选项

| 参数 | 说明 |
|---|---|
| `-t`, `--theme <名称>` | 背景主题。可选：`cream`(默认)、`sky`、`dark` |

### 示例

```bash
svg-picker home                  # 默认 cream 米黄主题
svg-picker home --theme sky      # 天蓝背景
svg-picker arrow -t dark         # 深色主题（短选项）
```

### 通过 `.env` 设置默认主题

如果不想每次都敲 `--theme`，可在运行 `svg-picker` 的目录下放一个 `.env` 文件：

```bash
cp .env.example .env       # 然后编辑 .env
```

```ini
# .env
SVG_PICKER_THEME=sky
```

优先级：**命令行 `--theme` → `.env` 中的 `SVG_PICKER_THEME` → `cream`**。`.env` 里写了非法值会在 stderr 警告并降级到内置默认。

### 步骤

1. 窗口打开，显示第一页 10 个匹配图标
2. 点击选中，再次点击取消选择
3. 按 `‹` / `›` 按钮或 `←` / `→` 键翻页 — 选中状态跨页保留
4. 点击 **Confirm** — SVG 源码打印到 stdout，窗口关闭
5. 直接关窗（点 X）= 取消，会在 stderr 打印一行 `[svg-picker] cancelled: ...`

---

## 给 AI Agent 用

### 作为 Claude Code Skill

将以下内容保存为 `~/.claude/skills/svg-picker.md`：

```markdown
# svg-picker

通过关键词搜索，以人类视觉选择方式获取 SVG 图标。

用法: svg-picker <关键词> [--theme cream|sky|dark]

人类从窗口中选择图标，SVG 源码输出到 stdout。
若窗口被关闭而未确认，stderr 会输出一行 `[svg-picker] cancelled: ...` —
读 stderr 可区分取消和崩溃。
```

### 程序化调用

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
    # 用户主动关闭窗口，未点 Confirm
    if "selected but not confirmed" in result.stderr:
        # 选了但没用上 —— 尊重取消意图，不要 fallback
        print("User cancelled with selections discarded")
    else:
        print("User cancelled without selection")
else:
    # 正常完成 —— result.stdout 是 SVG 源码
    svg_code = result.stdout
    # 每段格式:<!-- iconify_id -->\n<svg>...</svg>
```

---

## 对比

| | svg-picker | HULA（Atlassian） |
|---|---|---|
| 领域 | 图标选择 | 完整软件开发 |
| 范围 | 极简，单任务 | 完整 Agent 框架 |
| 人类角色 | 视觉裁判 | 规划 + 代码审查 |
| 部署方式 | pip install | Jira 插件 |
| 目标用户 | AI Agent | 人类工程师 |

两者共享同一核心理念：**人类判断提升 AI 输出质量**。

---

## 相关工作

- [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924) — ICSE SEIP 2025
- [acte](https://github.com/j66n/acte) — GUI 风格 Agent 工具框架
- [OpenUI](https://github.com/thesysdev/openui) — 生成式 UI 开放标准

---

## 开源协议

MIT
