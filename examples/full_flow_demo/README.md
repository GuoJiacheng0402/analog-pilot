# full_flow_demo — AnalogPilot 全流程小演示

一个五阶段、自包含的演示，带你过一遍 AnalogPilot 能在服务器上驱动的核心能力。每个阶段
相互独立、缺前提会自动跳过（并提示原因），所以即使只配好了一部分也能跑。

> 它**不碰你已有的 cell**：在一个一次性 cell（默认 `apilot_full_flow_demo`）里操作，结束
> 自动删除（`--keep` 可保留）。这是演示性质；真正的后端验收流程见
> [`../../tools/postlayout-verify/`](../../tools/postlayout-verify/)。

## 五个阶段

| 阶段 | 做什么 | 依赖 |
|---|---|---|
| 1 SKILL bridge | 在远端 Virtuoso 执行一条 SKILL（`1+2`） | 桥接已 start + CIW 已 load daemon |
| 2 Spectre 通道 | 理想 RC 低通 AC 扫频 → 算 −3dB（不需 PDK） | `APILOT_CADENCE_CSHRC` 已配 |
| 3 前端表征 | NMOS Id-Vgs 直流扫 → I-V 曲线写入 CSV（用 PDK 模型） | Spectre 通道 + `--model` |
| 4 版图 | `LayoutEditor` 摆放器件 + 布线 + 打孔 | 桥接 + tech-bound 设计库（`--lib`） |
| 5 DRC（可选） | strmout + Calibre DRC 验证阶段 4 的版图 | `--drc`，且服务器有 Calibre deck |

## 运行

```bash
cd analog-pilot && source .venv/bin/activate     # 确保已 pip install -e .
apilot start                                      # 并把打印的 load("...") 粘进 CIW

cd examples/full_flow_demo
python full_flow_demo.py \
    --lib   ANALOG \
    --model /SM01/home/<grade>/<你的学号>/Design/CSMC05_M3/Model/s05mixdtssa01v12.scs \
    --drc
```

常用参数：`--lib`（tech 绑定到 st02 的设计库，默认 `ANALOG` 或 `$APILOT_DEMO_LIB`）、
`--model`（PDK 模型，或设 `$APILOT_PDK_MODEL`）、`--drc`（加跑 DRC）、`--keep`（保留 demo
cell）、`--profile`（多服务器 profile）。

## 预期输出（实测于 SCUT 服务器）

```
Stage 1 — SKILL bridge
  execute('1+2') -> SkillResult(status=SUCCESS, output='3')
Stage 2 — Spectre channel — ideal RC low-pass AC sweep
  |H| low-f = 1.000, high-f = 0.0100; -3dB near 1.58 MHz (expect ~1 MHz)
Stage 3 — Front-end — NMOS Id-Vgs characterization
  Id-Vgs (Vds=3V, W/L=10u/1u): 13 points, Id(Vgs=3V) = 1266.89 uA   -> CSV
Stage 4 — Layout (LayoutEditor)
  LayoutEditor summary: {'ok': True, 'shapes': 3, 'vias': 2, 'instances': 1}
Stage 5 — DRC
  DRC: 0 hard violations (only soft/advisory checks, if any). CLEAN.
SUMMARY:  1 SKILL OK · 2 Spectre RC OK · 3 NMOS I-V OK · 4 Layout OK · 5 DRC OK
```

产物写入 `full_flow_demo_out/`（如 `nmos_idvgs.csv`），该目录已被 `.gitignore` 忽略。

## 这个 demo 演示了什么

- **远程 SKILL 自动化**（阶段 1、4）——任意 Virtuoso 操作都能脚本化。
- **前仿：testbench + 扫描 + 数据记录**（阶段 2、3）——直接驱动 Spectre、解析 PSF、出 CSV。
- **版图：摆放 / 布线 / 打孔**（阶段 4）——`LayoutEditor` 便捷层；它不是自动布线器，按你
  给定的几何精确绘制，再由 Calibre 验证（阶段 5）。

下一步想做完整的 DRC/LVS/PEX/后仿验收，见
[`skills/postlayout-verify`](../../skills/postlayout-verify/SKILL.md) 与
[`docs/04_后仿真流程指南.md`](../../docs/04_后仿真流程指南.md)。
