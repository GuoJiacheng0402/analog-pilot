# 03 · CSMC05_M3 PDK 备忘

本文档汇总 CSMC 0.5µm 工艺（库名 **`st02`**，PDK 目录 `CSMC05_M3`，3 层金属）的关键语义
注意事项。这些问题的共性在于：**多数不会报错，而是使工作点、阻值或相位产生静默错误**，
因此值得提前了解。

> 面向 AI 智能体的对应版本见 [`skills/csmc-pdk/SKILL.md`](../skills/csmc-pdk/SKILL.md)；
> 本文为说明性版本。

---

## 0. 首要步骤：dump 器件 CDF

不应默认 `w` 即为仿真宽度。进入本 PDK 后，应先用 SKILL dump 一个器件的 CDF 参数，确认
哪些参数带 `iPar(...)` 表达式、哪个真正进入 netlist：

```python
# 列出器件的合法 CDF 参数（名称、默认值、表达式）
client.execute_skill(
    'cdfGetBaseCellCDF(ddGetObj("st02" "mn"))~>parameters~>name')
```

CSMC `mn/mp` 的 CDF 关键片段如下：

```
("w"      "800n")              ; w 仅作显示，不进入 netlist
("fw"     "800n")              ; fw 为 finger width，真正进入 netlist
("simW"   "iPar(\"fw\")")      ; simW = fw（× fingers）
("fingers" "1")
```

**结论：CSMC 的仿真宽度为 `simW = fw × fingers`，而非 `w`。**

---

## 1. MOS 管尺寸：必须设置 `fw`

### 问题
仅设置 `w`/`l` 会导致所有管子在仿真中均为默认最小尺寸（约 `0.8u/1u`），**DC 工作点
全部错误**，且不报任何错误。

### 正确做法
```python
# 必须包含 fw；当 fingers>1 时 simW = fw × fingers
client.execute(  # 通过 SKILL 设置参数；务必包含 fw（仅设 w/l 会落到最小尺寸）
    '... dbReplaceProp(inst "fw" "string" "92u") ...')
```

### 流片时通过 fingers 拆分
例如目标 `W=92u`，可拆分为 `fw=8u, fingers=12 → simW=96u`。版图中 `fingers` 为 X 方向
并排的指数，`fw` 为单指的 Y 维宽度。

### 直接向 layout 注入 PCell 的完整 SKILL 语法
经反复调试确认的格式（参数列表为 `(name TYPE value)`，**而非** `(name value type)`；值为
SI 米制浮点，而非字符串 `"12u"`）：

```skill
dbCreateParamInstByMasterName(cv "st02" "mp" "layout" "M1"
  list(x_um y_um) "R0" 1
  list(list("w"       "float" w_meters)
       list("fw"      "float" fw_meters)
       list("l"       "float" 1.0e-6)
       list("fingers" "int"   N)))
```
要点：① 须使用 `"layout"` 视图（而非 ivpcell）；② type 使用 SKILL 类型名
`"float"/"int"/"string"/"boolean"`；③ 值使用米（`12.0e-6`）。

> 不想每次手写这段 SKILL，可用 `apilot.layout.LayoutEditor` 的 `place(...)` 封装
> （还含 `rect`/`path`/`via`/`label` 的布线/打孔/标签便捷方法）：
> `ed.place("st02","mn","M1",x,y, params={"w":92e-6,"fw":92e-6,"l":1e-6,"fingers":12})`。
> 用法见 [`skills/apilot/SKILL.md`](../skills/apilot/SKILL.md) 的「Layout editing」一节。

---

## 2. 电阻（rpoly2 / rhr1k）：通过几何定值，而非字符串

### 问题
仅传 `r="5K"` 只写入 OA 属性，PCell 几何不变，Calibre 按默认几何抽取，得到的阻值错误
（该错误往往到 PEX 阶段才暴露）。

### 正确做法
使用 `calculatedParam="Length"` + `segL`/`segW`（浮点 SI 米）+ `segments`/`ssegs`。参考值
（仅示意，具体需按目标阻值反推）：

| 电阻 | 器件 | 参数 | 抽取阻值 |
|---|---|---|---|
| 补偿电阻 Rz | rpoly2，13 段 | `segL≈9.35u` | ≈5001 Ω |
| 偏置电阻 R0 | rhr1k | `segL=2.0u, segW=1.44u` | ≈1496 Ω |
| BGR R3 | rhr1k | `segL=6.63u, segW=1.3u` | ≈5493 Ω |

> `segL` 取值需落在 **0.01µm 网格**上（如 `6.63u` 而非 `6.633u`），否则 DRC 报
> `offgrid_check`。验证阻值的可靠方法：建立 scratch cell，枚举不同 `segL/segW`，运行一次
> LVS 查看抽取阻值（先测量、再定值）。

---

## 3. 电容 cpip
- `PLUS`/`MINUS` 两个 pin 的 bbox 存在重叠（内/外两圈 A1 环），**不能按中心打 via**。应先
  dump master polygon 确认哪一圈为 PLUS、哪一圈为 MINUS，再从对应环接线。

---

## 4. BJT（qvp5）：面积比靠并联实现，LVS 使用 P1

### `m` 不放大版图
`qvp5` 的 `m`（默认 `area="25p"`、`m="1"`）**仅服务于仿真**，layout 不会自动生成 m 倍
面积。因此 BGR 中 `n=24` 的大管，**必须在版图中放置 24 个单位 `qvp5` 并联**，source CDL
亦写入 24 个并联实例，否则 LVS 实例数/面积不匹配。

### diode-connect 与温扫
- diode-connect 时 B、C 均接 GND；并联数 `m` 实现面积比，**不使用 area 参数**。
- 调用：`Q1 (C B E) qvp5 m=1`、`Q2 (...) qvp5 m=8`（仿真中）。
- DC 温扫语法：
  ```
  dc1 dc param=temp start=-40 stop=120 step=5 oppoint=screen annotate=status
  ```

### LVS 中 BJT 的 subtype 为 `P1`
`qvp5` 为**仿真模型名**；Calibre LVS deck 中的器件为：
```
DEVICE Q(P1) _qvp5 psub(C) nwelcon(B) pdifcon(E)
NETLIST MODEL "qvp5"
```
因此 source CDL 中 PNP 应写为 **`P1`**（带 `area=25p`），而非 `qvp5`。物理接法：
`E=pdifcon`（中心 5×5µm）、`B=nwelcon`、`C=psub`；emitter 从中心 A1 直接 via 至上层金属，
避免被环形 base/collector A1 短路（T3 跨越该环时不下 via）。

> 命名注意事项：课程描述常将小管称为 Q1、大管称为 Q2，但远端 schematic 实例名可能为
> `Q0(m=1)` 与 `Q1(m=24)`。**应以连接关系与 `m` 判断管子大小，而非实例名。**

---

## 5. 仿真模型文件（modelFiles）

- 模型文件：`/SM01/home/<grade>/<学号>/Design/CSMC05_M3/Model/s05mixdtssa01v12.scs`
- 需同时 include 两个 section：`section=tt`（MOSFET，典型角）与 `section=biptypical`（BJT）。
- **不应**再 include `section=bip` → `biptypical` 已嵌套包含带正确参数的 `bip`，重复 include
  会报 `Model qvp5 already defined`。
- SKILL 中设置：
  ```skill
  set_env_option(... '(("modelFiles" (("/.../s05mixdtssa01v12.scs" "tt"))))')
  ```
- 缺模型时报 `SFE-23: undefined model 'mp'/'mn'`，即 modelFiles / section 未正确配置。
- HSPICE 流程才使用 `h05mixdtssa01v12.lib`（section `tt`）；前仿与报告应优先使用 Spectre。

---

## 6. 激励源（analogLib vsource）参数命名

- **pulse 高低电平字段为 `val0`/`val1`**，而非 hspice 风格的 `v1`/`v2`。误写 `v1/v2` 会被
  **静默忽略**（不报错，但 pulse 不切换、输出不变化）。修正：
  ```skill
  dbReplaceProp(inst "val0" "string" "1")
  dbReplaceProp(inst "val1" "string" "3")
  ```
- pulse 参数名：`delay→td`、`rise→tr`、`fall→tf`、`width→twidth`、`period→per`。误用会报
  `CDF callback update failed for V1`。合法参数名可用
  `cdfGetBaseCellCDF(ddGetObj(lib cell))~>parameters` 列出。
- 任意 pulse 源至少需提供：`vdc, val0, val1, td, tr, tf, twidth, per, srcType="pulse"`。
- **AC 源**：在 pulse 的 srcType 下，Spectre 不将其视为 AC 源 → 应改为 `srcType="dc"` + `acm=1`。

---

## 7. 输出表达式 / 测量

- `add_output(... expr=...)`：表达式中的双引号需写为 `\\"`（writer 会将整个 expr 包裹在
  `"..."` 中）。
- **相位**：不应自行计算 `(180/π)*phase(...)`（会得到 -6300° 等错误值），应使用
  `phaseDegUnwrapped(VF("/vout"))`。相位裕度：
  ```
  PM = 180 + value(phaseDegUnwrapped(VF("/vout"))  cross(db20(VF("/vout")) 0 1 "falling"))
  ```
- **数值精度**（测量 mV 级信号或 TC 时需收紧，否则数值噪声会污染结果）：
  ```
  reltol=1e-6  vabstol=1e-9  iabstol=1e-15
  ```

---

## 8. 库与 cds.lib（参考）

工作目录 `~/Design/CSMC05_M3/` 下的 `cds.lib` 大致如下：

```
DEFINE cdsDefTechLib $CDSHOME/tools/dfII/etc/cdsDefTechLib
DEFINE analogLib     $CDSHOME/tools/dfII/etc/cdslib/artist/analogLib
DEFINE basic         $CDSHOME/tools/dfII/etc/cdslib/basic
DEFINE st02 ./st02
DEFINE <设计库> ./<设计库>
```

库的作用：
- `analogLib` —— 激励与理想元件（vsource、res、cap 等）
- `basic` —— GND/VDD/pin/wire
- `st02` —— CSMC 器件（`mn/mp/cpip/rpoly2/rhr1k/qvp5`，各有 `layout`+`ivpcell` 视图，
  LVS 有 `auLvs`/`auCdl`）
- 设计库 —— attach 至 `st02`（建库时不应勾选 Compression）

金属层命名（3 层金属）：`W1`=contact、`A1`=Metal1、`W2`=via1、`A2`=Metal2、`W3`=via2、
`T3`=Metal3（厚顶层，走 VDD/VSS rail 与长信号）；栅使用 Poly。

PDK 由学院统一安装在只读目录（形如 `/SM01/teaching/.../CSMC05_M3/`），并通过一个
`pdkInstall.sh` 在工作目录中创建软链（`~/Calibre`、`~/display.drf` 等），**不应删除这些
软链**。具体路径以课程公告为准。
