# examples

本目录保持精简：可直接参考的用法集中在各 skill（`../skills/`）中，此处仅提供「确认环境
连通」一类的最小可运行示例。

| 示例 | 作用 | 前提 |
|---|---|---|
| [`01_connect_smoke_test.py`](01_connect_smoke_test.py) | 连接桥接、执行一条 SKILL、进行连通性自检 | 已 `apilot start` 且 CIW 已 load daemon |
| [`full_flow_demo/`](full_flow_demo/) | 五阶段全流程小演示：SKILL · Spectre AC 扫 · NMOS Id-Vgs→CSV · 版图(摆放/布线/打孔) · DRC | 见该目录 README |

更多内容：
- 桥接引擎用法（执行 SKILL、运行 Spectre、解析 PSF、传文件）→ [`../skills/apilot/SKILL.md`](../skills/apilot/SKILL.md)
- CSMC05_M3 PDK 用法 → [`../skills/csmc-pdk/SKILL.md`](../skills/csmc-pdk/SKILL.md)
- 后仿完整流程 → [`../skills/postlayout-verify/SKILL.md`](../skills/postlayout-verify/SKILL.md)
