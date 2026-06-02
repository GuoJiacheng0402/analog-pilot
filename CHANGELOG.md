# Changelog

本项目的所有重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-06-02

### 新增
- **`apilot.layout.LayoutEditor`** —— 版图编辑便捷层：`place`（器件摆放）、`rect`/`path`
  （布线）、`via`（打孔，使用 techfile 标准 via 定义如 `M1_M2`/`M2_T3`）、`label`（为
  LVS 命名网络）、`clear`、`skill`（原始 SKILL 入口）。多次调用累积后一次性提交
  （`run_il_text`，一个往返、对大脚本稳健）；坐标单位为微米。它不是自动布线器——
  按你给定的几何精确绘制，由 Calibre DRC/LVS 验证。
- 已在 SCUT 服务器实测：通过 `LayoutEditor` 摆放 `mn` PCell + 画 A1/A2 金属线 +
  打 `M1_M2` via，strmout 后 Calibre DRC **硬规则 0 违规**。
- **`examples/full_flow_demo/`** —— 五阶段全流程小演示（SKILL / Spectre AC 扫 /
  NMOS Id-Vgs→CSV / 版图摆放·布线·打孔 / 可选 DRC），自包含、用一次性 cell、结束自动
  清理；已在服务器整体跑通（全部阶段 OK）。
- **`apilot selftest`** —— 一次性自检子命令：ssh / 隧道 / daemon / SKILL / spectre 通道。
- **最小 CI**（`.github/workflows/ci.yml`）：在干净机器上装包 + 导入 + 字节编译 + CLI 冒烟
  （Python 3.9 / 3.12），无需 EDA 服务器。

### 改进
- CLI 在配置缺失/错误时打印清晰的 `error:` 提示（而非 Python traceback）。
- `.env` 解析更稳健：仅当 `./.env` 含 `APILOT_` 键时才采用，避免误用其他项目的 `.env`。
- SKILL daemon 默认只绑定远端 `127.0.0.1`，经 SSH 隧道访问，避免在共享服务器上暴露执行端口。
- 远端文本部署改为经 SSH stdin 流式写入，避免较大 SKILL 脚本触发命令行长度限制。
- `LayoutEditor` 的布尔型 PCell 参数现正确生成 SKILL 的 `t`/`nil`。
- **README 视觉升级**：新增架构/流程图 [`assets/architecture.svg`](assets/architecture.svg)、
  徽章行、快速链接、「核心能力」与「已验证（实机端到端）」小节、可折叠目录树。

## [1.0.0] - 2026-06-02

首个公开版本。提炼自一次完整的《模拟集成电路原理与设计》课程设计实践
（2026 年春季学期，华南理工大学微电子学院）。

### 新增
- **自主实现的桥接引擎 `src/apilot/`**：基于 Cadence 公开的 SKILL IPC 设施
  （`ipcBeginProcess` / `evalstring`）从零实现，提供远程 SKILL 执行、SSH 隧道、
  Spectre 运行与 PSF 解析，并附 `apilot` CLI。
- **知识库 `docs/`**（7 篇）：总览与导航、服务器部署指南、常见问题与排错、
  CSMC05_M3 PDK 备忘、后仿真流程指南、仿真与验证方法学、协作与迭代约定。
- **原创技能 `skills/apilot`**：桥接引擎用法（SKILL 执行 + Spectre + PSF 解析）。
- **原创技能 `skills/csmc-pdk`**：CSMC05_M3 工艺的器件参数、电阻几何定值、
  BJT 建模（P1 / 并联）、vsource 命名、相位测量等约定。
- **原创技能 `skills/postlayout-verify`**：Calibre DRC/LVS/两步 PEX 与 Spectre
  后仿的完整流程。
- **工具 `tools/postlayout-verify/`**：配置驱动的运放 / 带隙基准后仿复现脚本
  （纯标准库，运行于服务器）。
- **工具 `tools/grab_vnc_screenshot.sh`**：经 SSH 抓取服务器 VNC 桌面截图。
- **模板与示例**：`docs/templates/`（csh 环境、`.cdsinit` 自动加载片段）、
  `.env.example`、`examples/`。
- **项目元文件**：`CONTRIBUTING.md`、`CITATION.cff`、`ACADEMIC_USE.md`、
  `assets/banner.svg`。

### 许可
- 本项目以 **GNU GPL v3.0** 发布，并附带 **GPL-3.0 第 7(b) 条「署名保留」附加条款**
  （见 `LICENSE` 顶部）。项目自身源码、文档与工具独立实现，未复制、嵌入或派生自第三方
  项目代码（见 `NOTICE`）。
- 学术使用须署名引用，详见 `ACADEMIC_USE.md`。

### 验证（已在 SCUT 服务器上端到端实测）
- **桥接 SKILL 通道**：`apilot start/status`、`execute()` 算术/字符串/错误捕获、多行
  `load` 均通过。
- **Spectre 独立通道**：csh 环境定位 spectre、运行 netlist、解析 PSF、频率/直流扫描，
  全部通过（理想 RC 低通 f3dB≈1MHz；NMOS Id-Vgs 特性曲线记录到 CSV）。
- **后端工具链**：Calibre DRC（自建 NMOS 硬规则全 0）、Calibre LVS（真实网络比对）、
  以及在真实全 R+C PEX 网表上的后仿（BGR 启动瞬态，Vref 稳定到 1.324V）均通过。

### 说明
- 本仓库已对全部站点相关信息做脱敏处理，仅含占位符；真实主机、账号、端口等
  请填入本地的 `.env` 与 `*.local.json`（均已被 `.gitignore` 忽略），请勿提交。

[1.1.0]: https://github.com/GuoJiacheng0402/analog-pilot/releases/tag/v1.1.0
[1.0.0]: https://github.com/GuoJiacheng0402/analog-pilot/releases/tag/v1.0.0
