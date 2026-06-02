# AGENTS.md — 面向 AI 智能体的项目指南

> 如果你是 AI 编码智能体（Claude Code、Cursor 等），请先完整阅读本文件。它说明 SCUT
> 服务器环境的特殊性、首次接入应执行的检查，以及常见错误的查阅位置。详细知识在
> [`docs/`](docs/) 与 [`skills/`](skills/) 中，本文件为入口与关键提示。

本项目使用户从本地工作站通过桥接引擎远程驱动微电子学院服务器上的 Cadence Virtuoso（执行
SKILL）与 Spectre（运行仿真）。**核心原则：所有 SKILL 均通过 `SkillClient` 执行，
不应直接 SSH 登录手动输入 SKILL。**

---

## 0. 两种工作模式

| 模式 | 用途 | 是否依赖远端 shell PATH |
|---|---|---|
| **SKILL 模式**（最常用） | 在 Virtuoso 中运行仿真、读写 schematic/layout/maestro | 否。SKILL 在 Virtuoso 主进程内执行，与远端登录 shell 的 csh/bash 及 PATH 无关 |
| **Spectre 独立通道**（按需） | 不启动 Virtuoso，直接将手写 netlist 提交给服务器的 `spectre`（适合批量并行） | 是。需要远端 shell 能定位到 `spectre`（见第 3 节 csh 相关问题） |

SCUT 课程设计中，多数任务使用 SKILL 模式即可。仅在需要绕开 maestro、大批量并行运行
netlist 时才使用 Spectre 独立通道。

---

## 1. 首次接入新会话的检查清单

1. **检查 `.env`**：`~/.apilot/.env`（或项目根目录的 `.env`）是否存在？
   `APILOT_REMOTE_HOST` / `APILOT_REMOTE_USER` 是否已填写？
   - 若无：`pip install -e .` → 向用户获取服务器与学号 → `cp .env.example ~/.apilot/.env` 后填写。
   - 确认 **`APILOT_DISABLE_CONTROL_MASTER=true` 已设置**（本环境必需，见第 3 节）。
2. **检查 SSH 连通性**：`ssh <host> echo ok`（应直接返回 `ok`，不应提示输入密码；若提示密码，需先执行 `ssh-copy-id`）。
3. **检查 Virtuoso 是否运行**：`ssh <host> "pgrep -f virtuoso"`。若无，需由用户在 VNC 桌面启动（命令行无法启动 GUI）。
4. **启动桥接**：`apilot start`。
5. **验证**：`apilot status` → 期望 `[tunnel] running` 与 `[daemon] OK`。
   - 出现 `[daemon] NO RESPONSE` 时，应首先询问用户「VNC 桌面中 Virtuoso 是否弹出了未关闭的对话框」（见第 3 节 GUI 阻塞）。
6. **连通性自检**：`SkillClient.from_env().execute_skill("1+2")` 应返回 `3`。

> 自动化：将 [`docs/templates/cdsinit_autoload.il`](docs/templates/cdsinit_autoload.il)
> 中的片段加入服务器 `~/.cdsinit`，即可在每次启动 Virtuoso 时自动加载 daemon，免去手动粘贴。

---

## 2. 本地环境的两个常见障碍

- **conda 干扰 venv**：若 `import apilot` 报 `ModuleNotFoundError`，通常是因为本地
  shell 默认 `conda activate base`，editable 安装写入的 `.pth` 未被 anaconda 的 site.py
  处理。临时方案：`export PYTHONPATH=<repo>/src`；根治方案：注释掉 shell 配置中的
  `conda activate base`。
- **macOS 自带 rsync 版本过旧**（2.6.9）：不支持 `--info=progress2` 等选项，必要时
  `brew install rsync`。

---

## 3. 容易导致阻塞或无效工作的关键问题（精简版）

> 完整、分类、附原始报错的版本见 [`docs/02_常见问题与排错.md`](docs/02_常见问题与排错.md)。
> 此处仅列出最容易导致 AI 浪费大量轮次的几条。

1. **GUI 对话框会导致 daemon 阻塞**。任何在 Virtuoso 中弹出模态表单的操作（`schViewToView`
   的八参形式、修改正在被 maestro 引用的 schematic、`maeRunSimulation` 触发的
   "Update and Run" 对话框等）都会**阻塞整条 SKILL 通道**，导致后续所有 `execute_skill`
   超时。服务器通常未安装 `xdotool/wmctrl`，`dismiss-dialog` 多数情况下不可用。
   - **处理方式**：出现超时或 `NO RESPONSE` 时，先请用户在 VNC 中检查并关闭未关闭的对话框；
     能使用无表单 API 时应避免使用会弹出表单的接口（例如生成 symbol 使用
     `schPinListToSymbol`，而非 `schViewToView`）。
2. **修改 schematic 前需确认没有处于活动状态的 maestro session**，否则会弹出 "re-netlist?"
   对话框导致阻塞。正确顺序：建立 schematic → 设置全部参数 → 再 `maeOpenSetup`。
3. **`APILOT_CADENCE_CSHRC` 不能填写学校的 `bashrc_cds`**。后者为 bash 语法，桥接以 csh 加载
   会报错。SKILL 模式无需此项（留空）；使用 Spectre 独立通道时，应基于
   [`docs/templates/cadence_env.csh.example`](docs/templates/cadence_env.csh.example)
   改写为 csh 版本。
4. **`bashrc_cds` 会设置 `LD_PRELOAD`（旧版 OpenSSL）**，影响当前 shell 的 git/curl 等工具。
   用于启动 Virtuoso 的 shell 在 source 后不应执行其他操作，且**不应**写入 `~/.bashrc`。
5. **CSMC PDK：MOS 需设置 `fw` 而非仅 `w`**，否则仿真中均为最小尺寸，DC 工作点错误。
   电阻需通过 `segL/segW` 定值，而非字符串 `r="5K"`。详见
   [`skills/csmc-pdk`](skills/csmc-pdk/SKILL.md) 与 [`docs/03_CSMC05_PDK备忘.md`](docs/03_CSMC05_PDK备忘.md)。
6. **BGR 测量温度系数（TC）必须使用启动瞬态**（每个温度点将 VDD 从 0 升至额定后取稳态），
   纯 DC 温扫会落入低压零电流分支，导致 TC 表现为数千 ppm/°C 的无效结果。

---

## 4. 关键约定

- **所有 SKILL 通过 `SkillClient.execute_skill(...)` 执行**；如需保留某段 SKILL 以便调试，
  使用 `runner.upload_text(SKILL, "/tmp/foo.il")` + `execute_skill('load("/tmp/foo.il")')`
  （桥接执行后会删除临时文件）。
- **进入新 PDK 的首要步骤**：dump 一个器件的 CDF，确认其 `simW`/`simL` 表达式（CSMC 为
  `simW = fw × fingers`），不应默认 `w` 即为仿真宽度。
- **读取真值，不应臆测**：使用 SKILL dump PDK 的真实参数名、合法取值与几何，不应凭训练
  记忆假设属性名。
- **小步可回退、双备份**：每到一个里程碑（DRC 清零、LVS CORRECT、PEX 成功等）即做本地与
  远端双备份，并将状态写回工作日志。详见 [`docs/06_协作与迭代约定.md`](docs/06_协作与迭代约定.md)。
- **后仿优先采用「直接 Spectre netlist + 自行解析 PSF」**，以规避 maestro 的 GUI 阻塞。

---

## 5. 技能与文档索引

| 任务 | 对应 skill / 文档 |
|---|---|
| 执行 SKILL、运行 Spectre、解析 PSF、传文件 | [`skills/apilot/SKILL.md`](skills/apilot/SKILL.md) |
| CSMC05_M3 PDK 用法与约定 | [`skills/csmc-pdk/SKILL.md`](skills/csmc-pdk/SKILL.md) |
| 后仿：Calibre + PEX + Spectre | [`skills/postlayout-verify/SKILL.md`](skills/postlayout-verify/SKILL.md) |
| 部署 / 连接 / 启动 | [`docs/01_服务器部署指南.md`](docs/01_服务器部署指南.md) |
| 报错查询 | [`docs/02_常见问题与排错.md`](docs/02_常见问题与排错.md) |
| 仿真方法学（开环 AC、启动瞬态 TC、并行） | [`docs/05_仿真与验证方法学.md`](docs/05_仿真与验证方法学.md) |

---

## 6. 新会话起始信息模板

建议用户在每次新对话开始时提供如下信息：

```
我在使用 analog-pilot 远程驱动微电子学院服务器上的 Cadence。请先阅读项目根目录的 AGENTS.md
与 docs/00_总览与导航.md。
- 当前阶段：<前仿 / 版图 / DRC / LVS / PEX / 后仿>
- 当前目标：<一句话>
- 桥接状态：<已 start / 未 start>，profile：<默认 / -p xxx>
环境特殊性以 AGENTS.md 第 3 节为准（GUI 会阻塞、CSMC 使用 fw 而非 w、TC 使用启动瞬态等）。
请先执行 apilot status 确认连接，再开始工作。
```
