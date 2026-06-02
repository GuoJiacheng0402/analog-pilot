<p align="center">
  <img src="assets/banner.svg" alt="AnalogPilot" width="100%"/>
</p>

<h1 align="center">AnalogPilot</h1>

<p align="center">
  <b>面向华南理工大学微电子学院 EDA 服务器的<br/>
  AI 智能体驱动的 Cadence 模拟/混合信号 IC 设计流程套件</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-blue.svg" alt="GPLv3"/></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+"/>
  <img src="https://img.shields.io/badge/PDK-CSMC%200.5%C2%B5m%20(CSMC05__M3)-orange" alt="CSMC05_M3"/>
  <img src="https://img.shields.io/badge/EDA-Virtuoso%20IC618%20%C2%B7%20Spectre%20%C2%B7%20Calibre-blueviolet" alt="EDA"/>
</p>

<p align="center">
  <a href="docs/00_总览与导航.md">文档</a> ·
  <a href="AGENTS.md">AGENTS</a> ·
  <a href="examples/full_flow_demo/">Demo</a> ·
  <a href="docs/02_常见问题与排错.md">常见问题</a> ·
  <a href="README.en.md">English</a>
</p>

---

本项目提供一套工具与文档，使用户能够从本地工作站通过 Python 与命令行远程驱动华南理工
大学微电子学院 EDA 服务器上的 Cadence Virtuoso（SKILL 执行）、Spectre 仿真与 Mentor
Calibre 物理验证，将原本依赖 VNC 图形界面手工操作的「原理图 → 前仿 → 版图 →
DRC/LVS/PEX → 后仿」流程，转化为可脚本化、可复现、可批量并行的自动化流程。

项目内容提炼自作者在 2026 年春季学期、于微电子学院完成《模拟集成电路原理与设计》课程
设计的全过程，目的是将其中验证有效的工程方法与常见错误的解决方案，沉淀为可复用的文档、
约定与工具，供后续使用者参考。详见文末 [项目来源](#项目来源)。

## 核心能力

- **一桥连通** —— 本地 Python / CLI 通过 SSH 远程执行 SKILL、运行 Spectre、调用 Calibre，无需常驻 GUI。
- **前仿自动化** —— 直接驱动 Spectre 跑 testbench 与参数扫描，解析 PSF，数据落地 CSV。
- **版图脚本化** —— `LayoutEditor` 程序化完成器件摆放、布线、打孔与标签（非自动布线器，按给定几何精确绘制）。
- **后端全流程** —— Calibre DRC / LVS / 两步 PEX + Spectre 后仿，配置驱动、可复现。
- **AI 友好** —— `skills/` 将服务器环境与 CSMC05_M3 PDK 约定提供给编码智能体（Claude Code / Cursor 等）。
- **实机验证** —— 代表性流程已在校园服务器上端到端实测通过（见 [已验证](#已验证实机端到端)）。

## 架构与流程

<p align="center">
  <img src="assets/architecture.svg" alt="AnalogPilot architecture and design flow" width="100%"/>
</p>

本地的 `apilot` 通过一条 SSH 隧道驱动服务器上的三类工具——Virtuoso（经 SKILL daemon）、
Spectre、Calibre——把「原理图 → 前仿 → 版图 → DRC → LVS → PEX → 后仿」整条流程脚本化。

## 适用对象与边界

- 适合：需要在微电子学院服务器上完成模拟/混合信号 IC 课程设计或科研全流程，并希望把
  流程脚本化、批量化、可复现的使用者；以及希望借助 AI 智能体辅助、需为其提供环境与
  PDK 上下文的使用者。
- 本项目**不包含**任何商业 PDK / 工艺库本体或受 NDA 约束的工艺数据；所有模型与规则文件
  均引用服务器上由学院统一安装的版本。
- 本项目**不替代设计决策**；它自动化流程中机械、重复的部分，使用户专注于电路设计本身。

> 许可与权属说明见 [`NOTICE`](NOTICE) 与文末 [原创性与权属说明](#原创性与权属说明)。

## 文档导航

| 目标 | 文档 |
|---|---|
| 从本地连接服务器、在 Virtuoso 中执行首条 SKILL | [`docs/01_服务器部署指南.md`](docs/01_服务器部署指南.md) |
| 按现象查询报错、卡死、异常的解决方案 | [`docs/02_常见问题与排错.md`](docs/02_常见问题与排错.md) |
| CSMC05_M3 PDK 的器件参数、电阻定值、BJT 与 netlist 约定 | [`docs/03_CSMC05_PDK备忘.md`](docs/03_CSMC05_PDK备忘.md) |
| 后仿流程：DRC → LVS → 两步 PEX → Spectre 后仿 | [`docs/04_后仿真流程指南.md`](docs/04_后仿真流程指南.md) |
| 仿真方法学：开环 AC 测增益/相位裕度、启动瞬态测温度系数、批量并行仿真 | [`docs/05_仿真与验证方法学.md`](docs/05_仿真与验证方法学.md) |
| 与 AI 协作及长周期迭代的工程约定 | [`docs/06_协作与迭代约定.md`](docs/06_协作与迭代约定.md) |
| 全部约定速查与总览 | [`docs/00_总览与导航.md`](docs/00_总览与导航.md) |
| 面向 AI 智能体的入口指南 | [`AGENTS.md`](AGENTS.md) |

## 快速开始

> 完整步骤（含每步预期输出、回滚方式与常见报错）见
> [`docs/01_服务器部署指南.md`](docs/01_服务器部署指南.md)。下文为最短路径。

**前提**：① 能够 `ssh <学号>@<服务器>` 登录服务器；② 服务器上有一个正在运行的
Virtuoso 进程（在 VNC 桌面中启动）。

```bash
# 1) 本地安装（建议使用独立 venv）
git clone https://github.com/GuoJiacheng0402/analog-pilot.git
cd analog-pilot
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2) 配置：生成模板并填写服务器与账号
apilot init <学号>@<服务器>              # 写出 ~/.apilot/.env
$EDITOR ~/.apilot/.env                   # 至少填写 APILOT_REMOTE_HOST / APILOT_REMOTE_USER

# 3) 配置免密登录（一次性）
ssh-copy-id <学号>@<服务器>

# 4) 启动桥接（建立 SSH 隧道并部署 SKILL daemon）
apilot start

# 5) 将 start 输出的 load("....il") 一行粘贴至 Virtuoso CIW，然后验证
apilot status                            # 期望 [tunnel] running / [daemon] OK
apilot selftest                          # 一次性自检全链路（ssh / daemon / SKILL / spectre）
```

```python
from apilot import SkillClient
client = SkillClient.from_env()
print(client.execute("1+2"))             # SkillResult(status=SUCCESS, output='3')
```

> 如需在每次启动 Virtuoso 时自动加载 daemon、免去手动粘贴，可将
> [`docs/templates/cdsinit_autoload.il`](docs/templates/cdsinit_autoload.il) 中的片段
> 加入服务器的 `~/.cdsinit`，详见部署指南。

## 已验证（实机端到端）

下列代表性结果在校园服务器（CSMC05_M3 工艺）上实测通过：

```text
$ apilot selftest
  [ok] ssh reachable      : <server>
  [ok] tunnel             : running
  [ok] daemon             : OK
  [ok] SKILL execute(1+2) : 3
  [ok] spectre channel    : found

$ python examples/full_flow_demo/full_flow_demo.py --lib ANALOG --drc
  1 SKILL        OK
  2 Spectre RC   OK   (-3dB ~ 1.58 MHz)
  3 NMOS I-V     OK   (Id @ Vgs=3V ~ 1267 uA  ->  CSV)
  4 Layout       OK   (place + route + via)
  5 DRC          OK   (0 hard violations)
```

一行体验全流程见 [`examples/full_flow_demo/`](examples/full_flow_demo/)。

## 为 AI 智能体加载 skills

[`skills/`](skills/) 目录为 [Claude Code](https://claude.com/claude-code) 等编码智能体
提供技能定义。将其链接至智能体的技能目录后，智能体即可获得本环境的上下文：

```bash
mkdir -p ~/.claude/skills
for s in apilot csmc-pdk postlayout-verify; do
  ln -sf "$(pwd)/skills/$s" ~/.claude/skills/$s
done
```

| skill | 作用 |
|---|---|
| [`skills/apilot`](skills/apilot/SKILL.md) | 桥接引擎用法：执行 SKILL、版图编辑（`LayoutEditor`）、运行 Spectre、解析 PSF |
| [`skills/csmc-pdk`](skills/csmc-pdk/SKILL.md) | CSMC05_M3 PDK 专属约定：finger width、电阻几何定值、BJT 建模、相位测量等 |
| [`skills/postlayout-verify`](skills/postlayout-verify/SKILL.md) | 后仿验证流程：Calibre DRC/LVS/PEX 与 Spectre 后仿，含配置驱动的复现脚本 |

## 仓库结构

<details>
<summary>展开目录树</summary>

```
analog-pilot/
├── README.md / README.en.md / AGENTS.md   项目说明与面向 AI 智能体的指南
├── LICENSE / NOTICE                        GPL-3.0（含第 7(b) 条「署名保留」附加条款）
├── ACADEMIC_USE.md                         学术使用与署名要求
├── CONTRIBUTING.md / CHANGELOG.md / CITATION.cff   贡献指南 / 变更记录 / 引用信息
├── pyproject.toml / .env.example           安装配置与连接配置模板（仅含占位符）
├── assets/                                 banner / architecture 图
├── docs/                                    知识库（中文，7 篇 + templates/）
├── skills/                                  供 AI 智能体加载（apilot / csmc-pdk / postlayout-verify）
├── src/apilot/                              自主实现的桥接引擎（SKILL 执行 + 版图编辑层 + Spectre + PSF + CLI）
├── tools/
│   ├── postlayout-verify/                   配置驱动的后仿复现脚本（运放 / 带隙基准通用）
│   └── grab_vnc_screenshot.sh               从服务器 VNC 桌面取图至本地
└── examples/                                最小可运行示例 + full_flow_demo/
```

</details>

## 项目来源

本项目源自作者在 2026 年春季学期、于华南理工大学微电子学院完成《模拟集成电路原理与
设计》课程设计的全过程——从一个运算放大器与一个带隙基准的原理图与前仿，到版图绘制、
Calibre DRC/LVS/PEX，再到 Spectre 后仿与前后仿对比。

课程设计真正的难点，往往不在电路本身，而在于与一套陌生的服务器环境、工艺库语义和工具
链反复磨合：一个忘记设置的 finger width，会让所有管子悄然回到最小尺寸；一个无人留意的
模态对话框，会让整条通道静默卡死；一次落入零电流分支的温度扫描，会让温度系数凭空虚高
数千倍。这些问题大多不报错，只是默默地让结果失真，往往要耗去数小时乃至数天才能定位。

这些经验如果只停留在个人工作日志中，后续使用者仍需重复定位同类问题。本项目将它们系统
整理为可复用的文档、约定与工具，使使用者能把更多时间投入到电路设计本身。

## 原创性与权属说明

**本项目是一个独立、自主实现的开源项目；项目自身源码、文档与工具未复制、嵌入或派生自
任何第三方项目代码。**

本仓库的主要内容均由本项目独立编写，包括：

- **自主实现的桥接引擎** [`src/apilot/`](src/apilot/)：基于 Cadence 公开的 SKILL IPC
  设施（`ipcBeginProcess` / `evalstring`）从零实现，提供远程 SKILL 执行、SSH 隧道、
  版图编辑便捷层（`LayoutEditor`：摆放 / 布线 / 打孔 / 标签）、Spectre 运行与 PSF 解析；
- 面向微电子学院服务器环境的全部文档知识库（[`docs/`](docs/)，共 7 篇）；
- 三个原创技能：[`apilot`](skills/apilot/SKILL.md)（引擎用法）、
  [`csmc-pdk`](skills/csmc-pdk/SKILL.md)（CSMC05_M3 工艺约定）、
  [`postlayout-verify`](skills/postlayout-verify/SKILL.md)（后仿验证流程）；
- 配置驱动的后仿复现工具 [`tools/postlayout-verify/`](tools/postlayout-verify/) 与辅助脚本
  [`tools/grab_vnc_screenshot.sh`](tools/grab_vnc_screenshot.sh)；
- 全部部署模板、配置示例与示例代码。

`ipcBeginProcess` / `evalstring` 是 Cadence Virtuoso 自带的公开 IPC 机制，并非任何
第三方项目的专有内容；本项目据此独立实现了自己的桥接引擎。
Python 运行依赖以 [`pyproject.toml`](pyproject.toml) 中声明为准。

## 学术使用与署名要求

如果你在课程设计、毕业设计、学位论文或任何学术成果中使用了本项目（代码、文档、约定或
方法论），**必须在报告/论文中明确署名引用本项目**，引用格式见 [`CITATION.cff`](CITATION.cff)。

① 本项目许可证为 **GPL-3.0**，并附带 **GPL-3.0 第 7(b) 条「署名保留」
附加条款**——复用本项目内容时应保留作者署名；② 学术诚信规范。在成果中使用他人
公开工作而不加说明，可能构成不当引用或剽窃。完整说明与可直接复制的署名文字见
[`ACADEMIC_USE.md`](ACADEMIC_USE.md)。

## 致谢

- 感谢陈教授在 2026 年春季学期《模拟集成电路原理与设计》课程中的耐心指导。

## 作者与许可

- 作者：**GuoJiacheng**（华南理工大学微电子学院）；部分代码与文档在 **Claude（Anthropic）**
  辅助下整理和编写。
- 许可：[GPL-3.0](LICENSE)，含 GPL-3.0 第 7(b) 条「署名保留」附加条款（见 LICENSE 顶部）。
- 贡献：欢迎补充新的问题记录、约定与工具脚本，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 引用：如在工作中使用本项目，可参考 [CITATION.cff](CITATION.cff)（GitHub 会据此显示
  "Cite this repository"）；版本变更见 [CHANGELOG.md](CHANGELOG.md)。
