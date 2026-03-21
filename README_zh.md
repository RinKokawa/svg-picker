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

- **原生 GUI** — PySide6 暗色主题窗口，无需浏览器
- **Iconify API** — 接入 150+ 图标集、50 万+ 图标
- **stdout 输出** — SVG 代码直接流入 AI 上下文
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
svg-picker <关键词>
```

示例：

```bash
svg-picker home
```

1. 窗口打开，显示匹配的图标
2. 点击选中一个或多个
3. 点击 **Confirm** — SVG 源码打印到 stdout，窗口关闭
4. AI Agent 收到 SVG 代码并用于代码中

---

## 给 AI Agent 用

### 作为 Claude Code Skill

将以下内容保存为 `~/.claude/skills/svg-picker.md`：

```markdown
# svg-picker

通过关键词搜索，以人类视觉选择方式获取 SVG 图标。

用法: svg-picker <关键词>

人类从窗口中选择图标，SVG 源码输出到 stdout。
```

### 程序化调用

```python
import subprocess

result = subprocess.run(["svg-picker", "home"], capture_output=True, text=True)
svg_code = result.stdout
# svg_code 包含原始 SVG 源码
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
