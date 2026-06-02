---
name: apilot
description: "Drive a remote Cadence Virtuoso via SKILL and run standalone Spectre simulations through AnalogPilot's bridge engine. TRIGGER when executing SKILL expressions remotely, starting/checking the bridge, loading .il scripts, transferring files to/from the EDA server, running a Spectre netlist outside the GUI, or parsing PSF output. Pairs with the csmc-pdk and postlayout-verify skills."
---

# AnalogPilot bridge engine

AnalogPilot's engine (`src/apilot/`) lets you execute SKILL in a remote Virtuoso
and run Spectre over SSH. It is an independent implementation built on Cadence's
public SKILL IPC facility (`ipcBeginProcess` / `evalstring`). Human-facing setup:
`docs/01_服务器部署指南.md`; pitfalls: `docs/02_常见问题与排错.md`.

## Before you start

1. `apilot` is a Python CLI installed via `pip install -e .` from the project root.
2. Config lives in `~/.apilot/.env` (or `./.env`); keys use the `APILOT_` prefix.
   On the campus servers, keep `APILOT_DISABLE_CONTROL_MASTER=true`.
3. A Virtuoso process must be running on the remote host, and its CIW must have
   loaded the bridge (`apilot start` prints the `load("...")` line to paste).

## CLI

```bash
apilot init <user@host>     # write ~/.apilot/.env
apilot start [-p PROFILE]   # open SSH tunnel + deploy daemon; prints the CIW load line
apilot status [-p PROFILE]  # check [tunnel] and [daemon]
apilot selftest [-p PROFILE]# one-shot check: ssh / tunnel / daemon / SKILL / spectre
apilot stop / restart
```

## Python API

```python
from apilot import SkillClient

client = SkillClient.from_env()          # reads ~/.apilot/.env
# (run `apilot start` and paste the load(...) line in the CIW first)

r = client.execute("1+2")                # -> SkillResult(status=SUCCESS, output='3')
print(r.ok, r.output)

# Everything in Virtuoso is reachable by sending SKILL strings, e.g.:
client.execute('dbReplaceProp(inst "val0" "string" "1")')

# Large / multi-line SKILL: upload to a file and load it (also the robust path
# when one socket message is not enough):
client.run_il_text(open("build_layout.il").read())

# File transfer:
client.upload_text(netlist_text, "/path/on/remote/input.scs")
client.download_file("/remote/result.csv", "local/result.csv")
```

> Each socket request carries **one** SKILL expression (one daemon write/flush).
> For anything multi-line or large, use `run_il_text(...)` / `load_il(...)`
> instead of `execute(...)` — this is also the recommended pattern for layout /
> schematic generation scripts.

## Layout editing — `apilot.layout.LayoutEditor`

A convenience layer over `execute()`/`run_il_text()` for programmatic layout:
place instances, draw metal rectangles/paths, drop vias, add labels. Calls are
accumulated and committed in ONE batch (efficient + robust for big scripts).
Coordinates are in microns. It is **not an auto-router** — it draws exactly the
geometry you specify; Calibre DRC/LVS then verify it.

```python
from apilot import SkillClient, LayoutEditor

c = SkillClient.from_env()
with LayoutEditor(c, "MyLib", "my_cell") as ed:        # commits on context exit
    ed.clear()                                          # wipe existing shapes/insts
    # 摆放 placement (CSMC MOS: pass fw too, in SI meters)
    ed.place("st02", "mn", "M1", 0, 0,
             params={"w": 5e-6, "fw": 5e-6, "l": 1e-6, "fingers": 1})
    # 布线 routing
    ed.rect("A1", 20, 0, 25, 1)                         # a metal-1 wire
    ed.rect("A2", 22, 0, 23, 6)
    ed.path("T3", [(0, 0), (0, 10), (5, 10)], width=0.6)  # a wide T3 wire
    # 打孔 vias (standard via defs from the techfile)
    ed.via("M1_M2", 22.5, 0.5)                          # A1 <-> A2
    ed.via("M2_T3", 1, 9)                               # A2 <-> T3
    # label a net for LVS (text on an *_text layer)
    ed.label("A1_text", "VOUT", 22.5, 0.5)
print(ed.last_summary)   # {'ok': True, 'shapes': 3, 'vias': 2, 'instances': 1}
```

API: `place(lib,cell,inst,x,y,orient="R0",params=...)`, `rect(layer,x0,y0,x1,y1)`,
`path(layer,points,width)`, `via(via_def,x,y,orient="R0")`,
`label(layer,text,x,y,height=0.1)`, `clear()`, `skill(raw)` (raw-SKILL escape
hatch), `commit()` / use as a `with` block. `params` is a dict (types inferred:
str→string, int→int, float→float) or explicit `[(name, type, value), ...]`.

CSMC notes (see the `csmc-pdk` skill): MOS must include **`fw`**; via defs are
e.g. `M1_M2`, `M2_T3`, `NDIFF_M1`, `PDIFF_M1`, `POLY1_M1_LV`; keep coordinates on
the **0.01µm grid**; LVS port names come from labels on `A1_text`/`A2_text`/
`A3_text`. After building, export with `strmout` and verify via the
`postlayout-verify` flow.

## Standalone Spectre

```python
from apilot import SpectreRunner, parse_psf_ascii

sim = SpectreRunner.from_env()           # APILOT_SPECTRE_BIN / APILOT_CADENCE_CSHRC honored
res = sim.run_netlist(netlist_text, run_name="ac_sweep", args="+aps")
print(res.ok, res.err[:400])
sim.fetch("/remote/.../psf/ac.ac", "local/ac.ac")
data = parse_psf_ascii(open("local/ac.ac").read())   # {signal: [values...]}
```

For the full DRC/LVS/PEX → post-sim flow and a config-driven driver, see the
`postlayout-verify` skill and `tools/postlayout-verify/`.

## Common gotchas (see docs/02 for the full list)

- `[daemon] NO RESPONSE` → first check the VNC desktop for an **unclosed modal
  dialog**; any SKILL that pops a form blocks the channel.
- Do not modify a schematic while a maestro session is alive (pops "re-netlist?").
- CSMC PDK: MOS needs `fw` (not just `w`); resistors are sized by `segL/segW`.
  See the `csmc-pdk` skill.
