---
name: postlayout-verify
description: "Post-layout verification flow on the School of Microelectronics, SCUT: Calibre DRC → LVS → two-step PEX (no-R/C then full R+C) → Spectre post-layout simulation, with a config-driven reproducible driver. TRIGGER when running or debugging Calibre DRC/LVS/PEX, generating a PEX netlist, mapping PEX device names for Spectre, building post-layout testbenches, comparing pre- vs post-layout metrics, or extracting OPA metrics (Adc/GBW/PM/Idc/SR) or BGR temperature coefficient (TC) from a PEX netlist. Use ALONGSIDE the apilot and csmc-pdk skills."
---

# Post-Layout Verification Skill

The end-to-end "layout → report-ready metrics" flow as actually run on the SCUT
servers, plus a config-driven driver that automates the last leg (PEX netlist →
metric CSV). Human-readable companion: `docs/04_后仿真流程指南.md`. Device-level
PDK rules: `../csmc-pdk/SKILL.md`.

## State machine (each step depends on the previous)

```
layout → DRC 0(0) → LVS CORRECT → PEX① no-R/C → align with pre-sim → PEX② full R+C → metrics
```

**Never enter PEX before LVS is CORRECT.**

## Two-step PEX (course requirement — understand WHY)

1. **no-R/C (SIMPLE)** — verifies the LVS/PEX flow + PDK file config is correct.
   Acceptance: post-sim of no-R/C should match pre-sim within expected tolerance.
   It is NOT about performance.
2. **full R+C** — only after step 1 passes; this shows the real parasitic impact.

## Work-dir naming convention

`work_<opa|bgr>_{drc,lvs,pex_no-rc,pex_r-plus-c}_<cell>/`. Use a distinct prefix
per circuit (e.g. `work_bgr_*`) so a new circuit never pollutes a delivered one.

## DRC

```bash
strmout -library <lib> -topCell <cell> -view layout -strmFile <cell>.gds \
        -dbuPerUU 1000 -scale 1.0 -runDir <work>      # NOT SKILL pipoStreamOut (crashes)
sed 's|CELLNAME|<cell>|g' deck > <cell>.drc.rules     # deck has its own LAYOUT PRIMARY
cd <work> && calibre -drc -hier -64 <cell>.drc.rules
# parse result.summary: "TOTAL DRC Results Generated: N (M)" → want 0 (0)
```
Fix order: bottom metal up (W1 → A1/W2 → A2/W3/T3). Quantize geometry to 0.01µm.
Use PDK-native gate contact (`connectGates="Top"`) instead of hand-drawn ones.

## LVS

```bash
strmout ...                          # refresh GDS with latest labels/pins
sed 's|CELLNAME|<cell>|g' deck > <cell>.lvs.rules
cp <cell>.cdl <cell>.spice           # deck expects .spice, not .cdl
cd <work> && calibre -lvs -hier -64 <cell>.lvs.rules
# read lvs.rep (CORRECT/INCORRECT); debug via lvs.rep.sp (extracted netlist)
```
- source CDL uses **deck subtype names**: MOS `NP/NN`, R `RL`(rpoly2)/`H1`(rhr1k),
  C `CP`(cpip), PNP `P1`(area=25p).
- **DRC clean ≠ no electrical short**: a same-layer long bus crossing devices
  shorts in LVS but not DRC. Route the long bus on another layer.
- Power/gnd/ref nets on T3; high-Z input nets on A2 (A1+W2+A2 access), with a
  short T3 bridge to hop over another input net if needed.
- Tie floating dummies and guard-ring A1 rings to VDD/VSS with a sparse via stack.
- For property mismatch on a passive, edit the **source CDL** to the extracted
  value; don't touch the layout.

## PEX (GUI runset batch — do NOT hand-write SVRF)

Hand-written `PEX NETLIST ...` lines fail with INP/PSS/SPC errors or even
SIGSEGV. Instead drive Calibre Interactive:

```bash
calibre -gui -pex -runset pex_gui.runset -batch      # edit runset fields, not the deck
```
- Ground warning fix: set `pexPexGroundName=1`, `pexPexGroundNameValue=VSS`
  (BGR: also `pexGroundNames=VSS`, `pexPEXGroundNetNames=VSS`).
- The no-R/C SIMPLE formatter does NOT support the `GROUND` keyword — leave that
  `PEX NETLIST SIMPLE ...` line untouched.

## Spectre post-sim (direct netlist, NOT maestro GUI)

- Map PEX device names `rpoly2/rhr1k/cpip` → builtin `resistor/capacitor` in a
  **simulation copy** (never edit the original PEX netlist). Handle `\` line
  continuations followed by blank lines.
- PEX subckt port order differs from schematic — instantiate per netlist:
  - OPA schematic `(VDD VIN1 VIN2 VOUT VSS)`, OPA PEX `(VDD VSS VOUT VIN1 VIN2)`,
    BGR PEX `(VREF VSS VDD)`.
- full R+C main netlist `include`s `.pex`/`.pxi` companions via RELATIVE paths —
  rewrite them to absolute paths if you run Spectre from a different dir.
- OPA: open-loop AC (1G H / 1G F) for Adc/GBW/PM; closed-loop unity follower
  transient for SR. BGR: **startup transient** temperature sweep for TC (NOT pure
  DC — that lands on a low-voltage zero-current branch). See
  `docs/05_仿真与验证方法学.md`.

## Config-driven driver (`tools/postlayout-verify/`)

Two stdlib-only drivers that run ON the server:

```bash
cd tools/postlayout-verify
cp configs/opa.example.json configs/opa.local.json   # edit cell names / paths
./run_opa_verify.sh --config configs/opa.local.json [--variants pex_rc]
./run_bgr_verify.sh --config configs/bgr.local.json --variants pex_rc [--rerun-pex]
```
Each run creates a fresh timestamped `runs/run_YYYYMMDD-HHMMSS/`, regenerates
testbenches, re-invokes Spectre, and re-parses the fresh PSF — no reuse of old
CSVs. Outputs: `opa_live_metrics.csv` / `bgr_live_metrics.csv`,
`temperature_points.csv`, `all_waveform_points.csv`, plus the `.scs` + logs +
PSF that produced them. `cds_lic_file`/`mgls_license_file` support a `{hostname}`
placeholder substituted at runtime.

## Acceptance

- OPA: full R+C post-sim 6/6 (Adc, GBW, PM, Idc, SR+, SR−).
- BGR: full R+C startup-transient TC, `TC = ΔVref/(mean(Vref)·ΔT)·1e6`.
- Report: pre/post comparison table + note explaining layout-driven iteration
  (e.g. parasitic IR-drop lowering the bias current).
