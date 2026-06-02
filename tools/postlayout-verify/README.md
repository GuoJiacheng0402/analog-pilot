# tools/postlayout-verify

一套**配置驱动**的后仿复现脚本，用于将「完成 DRC/LVS/PEX 之后，从 PEX 网表到报告指标
CSV」这一段流程自动化。两个 driver 均为**纯 Python 标准库**，设计为**运行于 Linux EDA
服务器**（具备 Spectre 与 PDK 的环境），无需 `pip install` 任何依赖。

> 概念、流程与注意事项见 [`../../docs/04_后仿真流程指南.md`](../../docs/04_后仿真流程指南.md)
> 与 [`../../skills/postlayout-verify/SKILL.md`](../../skills/postlayout-verify/SKILL.md)。

## 两个 driver

- **`opa_verify.py`** —— 对运放的 schematic 参考 / PEX no-R/C / PEX full R+C 网表运行
  Spectre，计算 `Adc / GBW / PM / Idc / SR+ / SR-` 六项指标。
- **`bgr_verify.py`** —— 对 BGR 的 PEX 网表运行**启动瞬态温度扫描**，计算 `Vref / Idd` 与
  温度系数 `TC = ΔVref / (mean(Vref)·ΔT) × 1e6`（ppm/°C）。

每次运行都新建带时间戳的 `runs/run_YYYYMMDD-HHMMSS/`，**重新生成 testbench、重新调用
Spectre、重新解析本次 PSF**，不复用旧 CSV/日志/raw。

## 用法

```bash
# 1) 复制配置模板并修改为实际值（*.local.json 已被 .gitignore 忽略，不会泄露）
cp configs/opa.example.json configs/opa.local.json
cp configs/bgr.example.json configs/bgr.local.json
$EDITOR configs/opa.local.json    # 修改 cell 名、netlist 路径、model/spectre 路径、license

# 2) 运行
./run_opa_verify.sh --config configs/opa.local.json                 # 运放：全部三档
./run_opa_verify.sh --config configs/opa.local.json --variants pex_rc   # 仅 full R+C
./run_bgr_verify.sh --config configs/bgr.local.json --variants pex_rc   # BGR 温扫
./run_bgr_verify.sh --config configs/bgr.local.json --variants pex_rc --rerun-pex  # 先重跑 PEX
```

> 亦支持以命令行参数覆盖部分配置项（`--model / --spectre / --pex-rc / --pex-cell` 等），
> 详见 `python3 opa_verify.py -h`。

## 配置要点

- `paths.model` —— PDK Spectre 模型文件（`s05mixdtssa01v12.scs`）。
- `paths.spectre` —— Spectre 可执行文件。
- `variants.*.include` / `.cell` —— 各档的 netlist 路径与 subckt 名。
- `variants.*.port_order` —— `schematic` 或 `pex`（两者端口顺序不同，见后仿流程指南）。
- `cadence.*` / `calibre.*` —— 环境与 license；`cds_lic_file` / `mgls_license_file`
  支持 `{hostname}` 占位符，运行时替换为当前主机名。
- BGR `--rerun-pex` 还需 `calibre.*` 与 `paths.gds/cdl/pex_deck/course_gui_runset`。

> 模板中所有站点相关值均以占位符（`<grade>`、`<student_id>`、`{hostname}`）表示，填入实际
> 值后请勿提交。

## 注意事项

- 原始 PEX 网表**不就地修改**；driver 将「映射器件别名 + 解析相对 include」后的副本写入
  run 目录，再提交给 Spectre。
- 默认端口顺序：运放 schematic `(VDD VIN1 VIN2 VOUT VSS)`、运放 PEX
  `(VDD VSS VOUT VIN1 VIN2)`、BGR PEX `(VREF VSS VDD)`。若 cell 端口顺序不同，需修改对应
  driver 中的 testbench 实例化行。
- 首次使用 BGR 时建议**不带** `--rerun-pex`，先确认现有 PEX 网表可端到端运行，再考虑重跑 PEX。
