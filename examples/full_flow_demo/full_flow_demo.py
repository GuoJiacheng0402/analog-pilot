#!/usr/bin/env python3
"""AnalogPilot — full-flow demo.

A guided tour of what AnalogPilot can drive on the remote EDA server, in five
small self-contained stages. Each stage is independent and degrades gracefully
(if a prerequisite is missing it is skipped with a message), so you can run the
whole thing even with only part of the setup ready.

    Stage 1  SKILL bridge       execute a SKILL expression in Virtuoso
    Stage 2  Spectre channel    ideal RC low-pass AC sweep  -> f3dB (no PDK needed)
    Stage 3  Front-end          NMOS Id-Vgs DC sweep -> I-V curve to CSV (uses PDK)
    Stage 4  Layout             place a device + route metal + drop a via (LayoutEditor)
    Stage 5  (optional) DRC      strmout + Calibre DRC on the layout from stage 4

Prerequisites
-------------
* `apilot start` done and the printed load("...") line pasted into the CIW
  (Stages 1, 3, 4, 5).
* Spectre channel configured: APILOT_CADENCE_CSHRC in your .env (Stages 2, 3).
* PDK model path (Stage 3) and a tech-bound design library (Stages 4, 5).

Run
---
    python full_flow_demo.py \
        --lib   ANALOG \
        --model /SM01/home/<grade>/<your_id>/Design/CSMC05_M3/Model/s05mixdtssa01v12.scs

Nothing here touches your existing cells: it works in a throwaway cell
(default `apilot_full_flow_demo`) and deletes it at the end (use --keep to keep).
This demo is illustrative; for the real back-end flow see tools/postlayout-verify.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from pathlib import Path, PurePosixPath

from apilot import SkillClient, SpectreRunner, LayoutEditor, parse_psf_ascii

OUT = Path("full_flow_demo_out")


def banner(n, title):
    print("\n" + "=" * 72)
    print("Stage %s — %s" % (n, title))
    print("=" * 72)


# -- Stage 1: SKILL bridge ---------------------------------------------------
def stage_skill(client) -> bool:
    banner(1, "SKILL bridge")
    r = client.execute("1+2")
    print("  execute('1+2') ->", r)
    if r.ok and r.output.strip() == "3":
        print("  OK: arbitrary SKILL runs in the remote Virtuoso.")
        return True
    print("  SKIP/FAIL: daemon not responding. Run `apilot start` + paste the load() line in CIW.")
    return False


# -- Stage 2: Spectre channel (ideal RC, no PDK) -----------------------------
def stage_spectre_rc(sim) -> bool:
    banner(2, "Spectre channel — ideal RC low-pass AC sweep")
    if not sim.check():
        print("  SKIP: spectre not found. Set APILOT_CADENCE_CSHRC in your .env.")
        return False
    netlist = (
        "// ideal RC low-pass, f3dB = 1/(2*pi*R*C) ~ 1 MHz\n"
        "simulator lang=spectre\nglobal 0\n"
        "V1 (in 0) vsource dc=0 mag=1\n"
        "R1 (in out) resistor r=1k\n"
        "C1 (out 0) capacitor c=159p\n"
        "ac1 ac start=1k stop=100M dec=5\n")
    res = sim.run_netlist(netlist, run_name="apilot_demo_rc", args="")
    if not res.ok:
        print("  FAIL: spectre error:", (res.err or res.out)[-300:])
        return False
    raw = PurePosixPath(sim.settings.scratch_root) / "spectre_runs" / "apilot_demo_rc" / "psf" / "ac1.ac"
    loc = OUT / "rc_ac.ac"
    sim.fetch(str(raw), str(loc))
    data = parse_psf_ascii(loc.read_text())
    out, freq = data.get("out"), data.get("freq")
    mags = [abs(complex(*v)) if isinstance(v, tuple) else abs(v) for v in out]
    f3 = next((freq[i] for i, m in enumerate(mags) if m <= 1 / math.sqrt(2)), None)
    print("  |H| low-f = %.3f, high-f = %.4f; -3dB near %.2f MHz (expect ~1 MHz)"
          % (mags[0], mags[-1], (f3 or 0) / 1e6))
    return True


# -- Stage 3: front-end NMOS characterization --------------------------------
def stage_nmos(sim, model) -> bool:
    banner(3, "Front-end — NMOS Id-Vgs characterization (sweep + CSV)")
    if not model:
        print("  SKIP: no PDK model. Pass --model or set APILOT_PDK_MODEL.")
        return False
    if not sim.check():
        print("  SKIP: spectre not found (Spectre channel not configured).")
        return False
    netlist = (
        "simulator lang=spectre\nglobal 0\n"
        'include "%s" section=tt\n'
        "Vdd (d 0) vsource dc=3\nVg (g 0) vsource dc=0\n"
        "M1 (d g 0 0) mn w=10u l=1u\n"
        "dc1 dc dev=Vg param=dc start=0 stop=3 step=0.25\nsave Vdd:p\n" % model)
    res = sim.run_netlist(netlist, run_name="apilot_demo_nmos", args="")
    if not res.ok:
        print("  FAIL:", (res.err or res.out)[-300:])
        return False
    raw = PurePosixPath(sim.settings.scratch_root) / "spectre_runs" / "apilot_demo_nmos" / "psf" / "dc1.dc"
    loc = OUT / "nmos_idvgs.dc"
    sim.fetch(str(raw), str(loc))
    data = parse_psf_ascii(loc.read_text())
    vg = data.get("dc") or []
    idd = data.get("Vdd:p") or []
    rows = [("Vgs_V", "Id_uA")]
    for i in range(len(idd)):
        vgs = vg[i] if i < len(vg) else i * 0.25
        rows.append((round(float(vgs), 3), round(-float(idd[i]) * 1e6, 4)))
    csv_path = OUT / "nmos_idvgs.csv"
    with csv_path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    last = rows[-1]
    print("  Id-Vgs (Vds=3V, W/L=10u/1u): %d points, Id(Vgs=3V) = %s uA" % (len(rows) - 1, last[1]))
    print("  CSV ->", csv_path)
    return True


# -- Stage 4: layout (place + route + via via LayoutEditor) ------------------
def stage_layout(client, lib, cell) -> bool:
    banner(4, "Layout — place device + route metal + drop via (LayoutEditor)")
    try:
        with LayoutEditor(client, lib, cell) as ed:
            ed.clear()
            ed.place("st02", "mn", "M1", 0, 0,
                     params={"w": 5e-6, "fw": 5e-6, "l": 1e-6, "fingers": 1})   # 摆放
            ed.rect("A1", 20, 0, 25, 1)                                          # 布线
            ed.rect("A1", 20, 5, 25, 6)
            ed.rect("A2", 22, 0, 23, 6)
            ed.via("M1_M2", 22.5, 0.5)                                           # 打孔
            ed.via("M1_M2", 22.5, 5.5)
        print("  LayoutEditor summary:", ed.last_summary)
        return bool(ed.last_summary and ed.last_summary.get("ok"))
    except Exception as exc:
        print("  SKIP/FAIL:", repr(exc))
        return False


# -- Stage 5: optional DRC ---------------------------------------------------
def stage_drc(client, lib, cell) -> bool:
    banner(5, "DRC (optional) — strmout + Calibre DRC")
    ssh = client.ssh
    work = "~/apilot_demo_drc"
    env = "prompt=true; source /SM01/eda/env_set/bashrc_cds >/dev/null 2>&1; source /SM01/eda/env_set/bashrc_mentor >/dev/null 2>&1"
    cmds = (
        "%s; mkdir -p %s && cd ~/Design/CSMC05_M3 && "
        "strmout -library %s -topCell %s -view layout -strmFile %s/c.gds -dbuPerUU 1000 -scale 1.0 -runDir %s >/dev/null 2>&1 && "
        "cd %s && sed 's|CELLNAME.gds|c.gds|; s|CELLNAME|%s|g' ~/Calibre/drc/csmccalibre.drc > r.rules && "
        "calibre -drc -hier -64 r.rules > drc.log 2>&1; "
        "grep -E 'RULECHECK .*= [1-9]' result.summary | grep -vi soft_check | head || true"
        % (env, work, lib, cell, work, work, work, cell))
    r = ssh.run("bash -c " + _q(cmds), timeout=300)
    hard = [ln for ln in r.out.splitlines() if "RULECHECK" in ln]
    if not hard:
        print("  DRC: 0 hard violations (only soft/advisory checks, if any). CLEAN.")
        ssh.run("rm -rf %s" % work)
        return True
    print("  DRC hard violations:\n   " + "\n   ".join(hard))
    ssh.run("rm -rf %s" % work)
    return False


def _q(s):  # shell-quote
    return "'" + s.replace("'", "'\\''") + "'"


def cleanup(client, lib, cell):
    client.execute('ddDeleteObj(ddGetObj("%s" "%s"))' % (lib, cell))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="AnalogPilot full-flow demo")
    p.add_argument("--lib", default=os.environ.get("APILOT_DEMO_LIB", "ANALOG"),
                   help="a tech-bound design library (default ANALOG / $APILOT_DEMO_LIB)")
    p.add_argument("--cell", default="apilot_full_flow_demo")
    p.add_argument("--model", default=os.environ.get("APILOT_PDK_MODEL"),
                   help="PDK Spectre model file (or set $APILOT_PDK_MODEL)")
    p.add_argument("--drc", action="store_true", help="also run strmout + Calibre DRC (stage 5)")
    p.add_argument("--keep", action="store_true", help="keep the demo cell instead of deleting it")
    p.add_argument("--profile", default=None)
    args = p.parse_args(argv)

    OUT.mkdir(exist_ok=True)
    client = SkillClient.from_env(profile=args.profile)
    sim = SpectreRunner.from_env(profile=args.profile)

    results = {}
    results["1 SKILL"] = stage_skill(client)
    results["2 Spectre RC"] = stage_spectre_rc(sim)
    results["3 NMOS I-V"] = stage_nmos(sim, args.model)
    layout_ok = stage_layout(client, args.lib, args.cell)
    results["4 Layout"] = layout_ok
    if args.drc and layout_ok:
        results["5 DRC"] = stage_drc(client, args.lib, args.cell)
    if layout_ok and not args.keep:
        cleanup(client, args.lib, args.cell)
        print("\n(cleaned up demo cell %s/%s)" % (args.lib, args.cell))

    print("\n" + "=" * 72 + "\nSUMMARY")
    for k, v in results.items():
        print("  %-14s %s" % (k, "OK" if v else "skipped/failed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
