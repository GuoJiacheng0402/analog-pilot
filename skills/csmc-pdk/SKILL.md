---
name: csmc-pdk
description: "CSMC 0.5µm (CSMC05_M3, library `st02`) PDK conventions and gotchas for the School of Microelectronics, SCUT. TRIGGER when setting MOS/resistor/capacitor/BJT device parameters, building schematics or layouts, writing Spectre netlists, configuring model files, or debugging wrong DC operating points / wrong extracted resistance / wrong phase with this PDK. Covers the fw-not-w finger-width rule, resistor sizing via segL/segW, BJT qvp5 (m doesn't scale layout, LVS subtype P1, biptypical), vsource val0/val1 naming, model file sections, phaseDegUnwrapped, and the dump-CDF-first rule. Use ALONGSIDE the apilot and postlayout-verify skills, not instead of them."
---

# CSMC05_M3 PDK Skill

CSMC 0.5µm process, library **`st02`**, 3 metal layers. This skill is the
"what's different about THIS PDK" layer. The general engine usage is in the
`virtuoso` and `spectre` skills. Human-readable companion:
`docs/03_CSMC05_PDK备忘.md`.

Most of these gotchas **do not raise an error** — they silently corrupt your
operating point, resistance, or phase. So apply them proactively.

## Rule 0 — dump the CDF before assuming anything

Never assume `w` is the simulated width. First dump a device's CDF and read
which params carry `iPar(...)` expressions:

```python
client.execute_skill('cdfGetBaseCellCDF(ddGetObj("st02" "mn"))~>parameters~>name')
```

CSMC `mn/mp`: `w` is display-only; `fw` (finger width) goes into the netlist;
`simW = iPar("fw")` × `fingers`.

## MOS sizing — always set `fw`

Setting only `w`/`l` leaves every device at minimum size in simulation → DC OP
all wrong, no error.

```python
client.execute('...set w/l/fw/fingers via SKILL...')  # fw is REQUIRED (w/l alone -> min size)
```

PCell injection into a layout (param list is `(name TYPE value)`, values in SI
meters, view must be `"layout"`):

```skill
dbCreateParamInstByMasterName(cv "st02" "mp" "layout" "M1"
  list(x_um y_um) "R0" 1
  list(list("w" "float" w_m) list("fw" "float" fw_m)
       list("l" "float" 1.0e-6) list("fingers" "int" N)))
```

## Resistors — size by geometry, not by `r="..."`

`r="5K"` only writes an OA property; Calibre extracts the default geometry.
Use `calculatedParam="Length"` + `segL`/`segW` (SI float) + `segments`/`ssegs`.
Quantize `segL` to the **0.01µm grid** (e.g. `6.63u`, not `6.633u`) or DRC flags
`offgrid_check`. Verify by extracting in a scratch cell ("measure, then commit").

## Capacitor cpip

`PLUS`/`MINUS` pin bboxes overlap (inner/outer A1 rings). Dump the master polygon
to learn which ring is which; tap the correct ring — don't via at the center.

## BJT qvp5 — `m` doesn't scale layout; LVS uses `P1`

- `m` serves simulation only; layout is NOT scaled. An area ratio `n` must be
  built as **n parallel unit `qvp5` instances** (layout AND source CDL).
- LVS deck device: `DEVICE Q(P1) _qvp5 psub(C) nwelcon(B) pdifcon(E)` /
  `NETLIST MODEL "qvp5"`. So **source CDL writes `P1` (area=25p), not `qvp5`**.
- Connections: `E=pdifcon` (center 5×5µm), `B=nwelcon`, `C=psub`. Route the
  emitter from the center A1 straight up via to metal so the ring base/collector
  A1 doesn't short it (don't via where T3 crosses the ring).
- Naming trap: course text may call the small device Q1 and big one Q2, but the
  schematic instance names may be `Q0(m=1)` / `Q1(m=24)`. Judge size by `m` and
  connectivity, not by instance name.

## Model files / sections

Model: `.../Design/CSMC05_M3/Model/s05mixdtssa01v12.scs`. Include
`section=tt` (MOS) **and** `section=biptypical` (BJT). **Do NOT also include
`section=bip`** → `Model qvp5 already defined`. Missing model → `SFE-23
undefined model 'mp'/'mn'` means sections aren't wired up. HSPICE flow uses
`h05mixdtssa01v12.lib` (section `tt`) — prefer Spectre for pre-sim/report.

```skill
set_env_option(... '(("modelFiles" (("/.../s05mixdtssa01v12.scs" "tt"))))')
```

## vsource (analogLib) parameter names

- Pulse high/low are **`val0`/`val1`**, NOT hspice-style `v1`/`v2` (wrong names
  are silently swallowed → pulse never toggles). Fix:
  `dbReplaceProp(inst "val0" "string" "1")` / `... "val1" ... "3"`.
- Pulse timing: `td/tr/tf/twidth/per` (not delay/rise/fall/width/period). Wrong
  name → `CDF callback update failed for V1`.
- Minimum pulse args: `vdc, val0, val1, td, tr, tf, twidth, per, srcType="pulse"`.
- AC source: under pulse `srcType`, Spectre won't treat it as AC → use
  `srcType="dc"` + `acm=1`.

## Measurement

- `add_output(... expr=...)`: escape inner double-quotes as `\\"`.
- Phase: use `phaseDegUnwrapped(VF("/vout"))` (DIY `(180/π)*phase(...)` gives
  garbage like −6300°). PM:
  `180 + value(phaseDegUnwrapped(VF("/vout")) cross(db20(VF("/vout")) 0 1 "falling"))`.
- mV-level / TC measurements: tighten `reltol=1e-6 vabstol=1e-9 iabstol=1e-15`.

## Metal stack (3 metals)

`W1`=contact, `A1`=Metal1, `W2`=via1, `A2`=Metal2, `W3`=via2, `T3`=Metal3 (thick
top: VDD/VSS rails + long signals). W2 vias strictly `0.55×0.55`, W3 vias
`0.6×0.6`. Power/ground/reference nets ride T3; high-Z input nets ride A2.

## See also

- DRC/LVS/PEX/post-sim pitfalls: `../postlayout-verify/SKILL.md`,
  `docs/02_常见问题与排错.md`.
- Engine API: `../apilot/SKILL.md`.
