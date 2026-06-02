#!/usr/bin/env python3
# Copyright (c) 2026 GuoJiacheng and the analog-pilot contributors.
# Licensed under the GNU GPL v3.0 with an additional attribution term (GPL-3.0 Section 7(b)). See LICENSE.
"""OPA post-layout verification driver.

Project : analog-pilot
Author  : GuoJiacheng
Source  : https://github.com/GuoJiacheng0402/analog-pilot
License : GPL-3.0-only with a Section 7(b) attribution term (see LICENSE and NOTICE)

Intended host: a Linux EDA server with Cadence Spectre and the analog PDK
installed. A typical invocation is:

    ./run_opa_verify.sh --config ../configs/opa.example.json

For each selected variant (schematic reference / PEX no-R/C / PEX full R+C),
the script regenerates a Spectre testbench, runs Spectre against the
current netlist, parses the freshly produced PSF ASCII raw data, and writes
both a compact metrics CSV and a long waveform-points CSV. No previously
generated CSV, screenshot, or raw file is reused.
"""

from __future__ import print_function

import argparse
import csv
import datetime as _dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_NAME = "analog-pilot"
PROJECT_REPO = "https://github.com/GuoJiacheng0402/analog-pilot"
PROJECT_AUTHOR = "GuoJiacheng"
PROJECT_LICENSE = "GPL-3.0-only"
PROJECT_COPYRIGHT = "Copyright 2026 GuoJiacheng"



def _path(value):
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


MODEL = _path("~/Design/CSMC05_M3/Model/s05mixdtssa01v12.scs")
SCH_OPEN = _path("~/simulation/tb_opa_open/spectre/schematic/netlist/input.scs")
PEX_NORC = _path("~/work_opa_pex_no-rc_opa_postlayout/opa_postlayout.norc.simple.scs")
PEX_RC = _path("~/work_opa_pex_r-plus-c_opa_postlayout/opa_postlayout.pex.netlist")

SPECTRE = Path(os.environ.get("SPECTRE_BIN", "spectre"))
ROOT = _path(os.environ.get("OPA_VERIFY_RUN_ROOT", "~/opa_verify"))
RUNS = ROOT / "runs"
CADENCE_HOME = os.environ.get("CADENCE_HOME", "")
MMSIMHOME = os.environ.get("MMSIMHOME", "")
CDS_LIC_FILE = os.environ.get("CDS_LIC_FILE", "")
VERIFY_LD_PRELOAD = os.environ.get("VERIFY_LD_PRELOAD", "")
REPORTS = {
    "drc": None,
    "lvs": None,
    "pex_log": None,
    "lvs_cell": "opa_postlayout",
}


VARIANTS = {
    "schematic_ref": {
        "title": "Pre-sim schematic: opa_v1, L=1u",
        "cell": "opa_v1",
        "include": SCH_OPEN,
        "port_order": "schematic",
    },
    "pex_norc": {
        "title": "PEX no-R/C: opa_postlayout",
        "cell": "opa_postlayout",
        "include": PEX_NORC,
        "port_order": "pex",
    },
    "pex_rc": {
        "title": "PEX full R+C: opa_postlayout",
        "cell": "opa_postlayout",
        "include": PEX_RC,
        "port_order": "pex",
    },
}


SPEC = [
    ("Adc_dB", "Adc", ">60 dB", lambda x: x > 60.0),
    ("GBW_MHz", "GBW", ">50 MHz", lambda x: x > 50.0),
    ("PM_deg", "PM", ">60 deg", lambda x: x > 60.0),
    ("Idc_uA", "Idc", "<150 uA", lambda x: x < 150.0),
    ("SR_pos_V_us", "SR+", ">30 V/us", lambda x: x > 30.0),
    ("SR_neg_V_us", "SR-", ">30 V/us", lambda x: x > 30.0),
]


def load_json_config(path):
    with _path(path).open() as f:
        return json.load(f)


def apply_config(config):
    global MODEL, SPECTRE, ROOT, RUNS, CADENCE_HOME, MMSIMHOME, CDS_LIC_FILE, VERIFY_LD_PRELOAD
    paths = config.get("paths", {})
    cadence = config.get("cadence", {})

    if "model" in paths:
        MODEL = _path(paths["model"])
    if "spectre" in paths:
        SPECTRE = _path(paths["spectre"])
    if "run_root" in paths:
        ROOT = _path(paths["run_root"])
        RUNS = ROOT / "runs"

    CADENCE_HOME = cadence.get("cadence_home", CADENCE_HOME)
    MMSIMHOME = cadence.get("mmsim_home", MMSIMHOME)
    CDS_LIC_FILE = cadence.get("cds_lic_file", CDS_LIC_FILE)
    VERIFY_LD_PRELOAD = cadence.get("ld_preload", VERIFY_LD_PRELOAD)

    for name, patch in config.get("variants", {}).items():
        if name not in VARIANTS:
            raise SystemExit("config has unknown OPA variant %s" % name)
        for key in ("title", "cell", "port_order"):
            if key in patch:
                VARIANTS[name][key] = patch[key]
        if "include" in patch:
            VARIANTS[name]["include"] = _path(patch["include"])

    reports = config.get("reports", {})
    for key in ("drc", "lvs", "pex_log"):
        if reports.get(key):
            REPORTS[key] = _path(reports[key])
    if reports.get("lvs_cell"):
        REPORTS["lvs_cell"] = reports["lvs_cell"]


def apply_cli_overrides(args):
    global MODEL, SPECTRE, ROOT, RUNS
    if args.model:
        MODEL = _path(args.model)
    if args.spectre:
        SPECTRE = _path(args.spectre)
    if args.run_root:
        ROOT = _path(args.run_root)
        RUNS = ROOT / "runs"
    if args.schematic_netlist:
        VARIANTS["schematic_ref"]["include"] = _path(args.schematic_netlist)
    if args.pex_norc:
        VARIANTS["pex_norc"]["include"] = _path(args.pex_norc)
    if args.pex_rc:
        VARIANTS["pex_rc"]["include"] = _path(args.pex_rc)
    if args.schematic_cell:
        VARIANTS["schematic_ref"]["cell"] = args.schematic_cell
    if args.pex_cell:
        VARIANTS["pex_norc"]["cell"] = args.pex_cell
        VARIANTS["pex_rc"]["cell"] = args.pex_cell
        REPORTS["lvs_cell"] = args.pex_cell


def executable_available(path):
    value = str(path)
    return Path(value).exists() or shutil.which(value) is not None


def spectre_env():
    env = os.environ.copy()
    hostname = subprocess.check_output(["hostname"], universal_newlines=True).strip()
    env.update({"LANG": "C", "CDS_AUTO_64BIT": "ALL", "CDS_LIC_ONLY": "1", "HOSTNAME": hostname})
    if CADENCE_HOME:
        env["CADHOME"] = CADENCE_HOME
    if MMSIMHOME:
        env["MMSIMHOME"] = MMSIMHOME
        env["PATH"] = env.get("PATH", "") + ":" + MMSIMHOME + "/bin:" + MMSIMHOME + "/tools/relxpert/bin"
    if CDS_LIC_FILE:
        env["CDS_LIC_FILE"] = CDS_LIC_FILE.format(hostname=hostname)
    if VERIFY_LD_PRELOAD:
        env["LD_PRELOAD"] = VERIFY_LD_PRELOAD
    return env


def fmt_si(value, unit):
    if unit == "Hz":
        if abs(value) >= 1e6:
            return "%.6g MHz" % (value / 1e6)
        if abs(value) >= 1e3:
            return "%.6g kHz" % (value / 1e3)
        return "%.6g Hz" % value
    if unit == "s":
        if abs(value) < 1e-6:
            return "%.6g ns" % (value * 1e9)
        return "%.6g us" % (value * 1e6)
    if unit == "V":
        return "%.8g V" % value
    if unit == "A":
        return "%.8g A" % value
    return "%.8g %s" % (value, unit)


def sanitize_pex_for_spectre(text, source_path, cell):
    base = str(source_path.parent)
    text = re.sub(
        r'include\s+"(%s\.pex\.netlist(?:\.pex|\.%s\.pxi))"' % (re.escape(cell), re.escape(cell)),
        lambda m: 'include "%s/%s"' % (base, m.group(1)),
        text,
    )
    text = re.sub(r"\\\n[ \t]*\n", "\\\n", text)
    text = re.sub(r"(\)\s+)rpoly2(\s+r=)", r"\1resistor\2", text)
    text = re.sub(r"(\)\s+)rhr1k(\s+r=)", r"\1resistor\2", text)
    text = re.sub(r"(\)\s+)cpip(\s+c=)", r"\1capacitor\2", text)
    return text


def prepare_include(variant, run_dir):
    info = VARIANTS[variant]
    source = Path(info["include"])
    text = source.read_text(errors="replace")
    if info["port_order"] == "schematic":
        cell = info["cell"]
        m = re.search(r"(?ms)^subckt\s+%s\b.*?^ends\s+%s\s*$" % (re.escape(cell), re.escape(cell)), text)
        if not m:
            raise RuntimeError("Cannot find subckt %s in %s" % (cell, source))
        text = "simulator lang=spectre\n" + m.group(0) + "\n"
    else:
        text = sanitize_pex_for_spectre(text, source, info["cell"])
    dest = run_dir / ("%s_include.scs" % variant)
    dest.write_text(text)
    return dest


def write_tb_ac(variant, include_file, run_dir):
    info = VARIANTS[variant]
    cell = info["cell"]
    if info["port_order"] == "pex":
        inst = "X1 (vdd 0 vout vinm vinp) %s" % cell
        order = "PEX order: (VDD VSS VOUT VIN1 VIN2)"
    else:
        inst = "X1 (vdd vinm vinp vout 0) %s" % cell
        order = "schematic order: (VDD VIN1 VIN2 VOUT VSS)"
    path = run_dir / ("tb_ac_%s.scs" % variant)
    path.write_text(
        """simulator lang=spectre
global 0
include "%s" section=tt
include "%s"

// %s
%s
Ccm (vinm 0) capacitor c=1G
Cload (vout 0) capacitor c=2p
Rload (vout 0) resistor r=1M
Lfb (vout vinm) inductor l=1G
Vin (vinp 0) vsource dc=2 type=dc mag=1
VDD (vdd 0) vsource dc=4 type=dc

simulatorOptions options psfversion="1.4.0" reltol=1e-3 vabstol=1e-6 \\
    iabstol=1e-12 temp=27 tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 \\
    maxnotes=20 maxwarns=20 digits=5 cols=80 pivrel=1e-3 checklimitdest=psf
ac ac start=1 stop=1G dec=30 annotate=status
dcOp dc write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status
save vout vinm vinp VDD:p
saveOptions options save=allpub
"""
        % (MODEL, include_file, order, inst)
    )
    return path


def write_tb_tran(variant, include_file, run_dir):
    info = VARIANTS[variant]
    cell = info["cell"]
    if info["port_order"] == "pex":
        inst = "X1 (vdd 0 vout vout vstim) %s" % cell
        order = "PEX order: (VDD VSS VOUT VIN1 VIN2)"
    else:
        inst = "X1 (vdd vout vstim vout 0) %s" % cell
        order = "schematic order: (VDD VIN1 VIN2 VOUT VSS)"
    path = run_dir / ("tb_tran_%s.scs" % variant)
    path.write_text(
        """simulator lang=spectre
global 0
include "%s" section=tt
include "%s"

// %s
%s
Cload (vout 0) capacitor c=2p
Rload (vout 0) resistor r=1M
VDD (vdd 0) vsource dc=4 type=dc
Vin (vstim 0) vsource dc=1 type=pulse delay=50n val0=1 val1=3 period=2u \\
    rise=10p fall=10p width=1u

simulatorOptions options psfversion="1.4.0" reltol=1e-3 vabstol=1e-6 \\
    iabstol=1e-12 temp=27 tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 \\
    maxnotes=20 maxwarns=20 digits=5 cols=80 pivrel=1e-3 checklimitdest=psf
dcOp dc write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status
tran tran stop=4u errpreset=conservative annotate=status maxiters=5
save vout vstim VDD:p
saveOptions options save=allpub
"""
        % (MODEL, include_file, order, inst)
    )
    return path


def run_spectre(tb, run_dir):
    raw = run_dir / (tb.stem + ".raw")
    log = run_dir / (tb.stem + ".log")
    cmd = [
        str(SPECTRE),
        "-64",
        str(tb),
        "+escchars",
        "+log",
        str(log),
        "-format",
        "psfascii",
        "-raw",
        str(raw),
        "+preset=ax",
        "+mt",
        "+lqtimeout",
        "900",
        "-maxw",
        "5",
        "-maxn",
        "5",
        "+logstatus",
    ]
    print("  [run] %s" % " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(run_dir),
        env=spectre_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        raise RuntimeError("Spectre failed: %s" % tb)
    print("  [ok] raw=%s" % raw)
    return raw


def parse_psf_file(path):
    text = Path(path).read_text(errors="replace")
    lines = text.splitlines()
    sections = {}
    for i, line in enumerate(lines):
        s = line.strip()
        if s in ("HEADER", "TYPE", "SWEEP", "TRACE", "VALUE", "END"):
            sections[s] = i
    if "VALUE" not in sections:
        return {}
    if "SWEEP" in sections:
        return parse_swept(lines, sections)
    return parse_nonswept(lines, sections)


def parse_swept(lines, sections):
    n = len(lines)
    sweep_var = None
    for i in range(sections["SWEEP"] + 1, sections.get("TRACE", sections["VALUE"])):
        m = re.match(r'"([^"]+)"', lines[i].strip())
        if m:
            sweep_var = m.group(1)
            break
    if not sweep_var:
        return {}
    trace_names = []
    if "TRACE" in sections:
        for i in range(sections["TRACE"] + 1, sections["VALUE"]):
            m = re.match(r'"([^"]+)"', lines[i].strip())
            if m:
                trace_names.append(m.group(1))
    data = {sweep_var: []}
    for name in trace_names:
        data[name] = []
    for i in range(sections["VALUE"] + 1, sections.get("END", n)):
        s = lines[i].strip()
        if not s or s == "END":
            break
        m = re.match(r'"([^"]+)"\s+\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)', s)
        if m:
            name = m.group(1)
            if name in data:
                data[name].append(complex(float(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r'"([^"]+)"\s+([-+0-9.eE]+)', s)
        if m:
            name = m.group(1)
            if name in data:
                data[name].append(float(m.group(2)))
    return data


def parse_nonswept(lines, sections):
    n = len(lines)
    data = {}
    for i in range(sections["VALUE"] + 1, sections.get("END", n)):
        s = lines[i].strip()
        if not s or s == "END":
            break
        m = re.match(r'^"([^"]+)"\s+(?:"[^"]+"\s+)([-+0-9.eE]+)', s)
        if m:
            data[m.group(1)] = float(m.group(2))
            continue
        m = re.match(r'^"([^"]+)"\s+([-+0-9.eE]+)', s)
        if m:
            data[m.group(1)] = float(m.group(2))
    return data


def parse_raw_dir(raw_dir):
    raw_dir = Path(raw_dir)
    merged = {}
    for name in ("dcOp.dc", "dc.dc", "spectre.dc"):
        p = raw_dir / name
        if p.exists():
            for k, v in parse_psf_file(p).items():
                merged["dc_" + k] = v
            break
    for name in ("ac.ac", "ac.ac.ac"):
        p = raw_dir / name
        if p.exists():
            for k, v in parse_psf_file(p).items():
                merged["ac_" + k] = v
            break
    for name in ("tran.tran.tran", "tran.tran"):
        p = raw_dir / name
        if p.exists():
            merged.update(parse_psf_file(p))
            break
    return merged


def unwrap_phase(values):
    raw = [math.degrees(math.atan2(v.imag, v.real)) for v in values]
    if not raw:
        return []
    out = [raw[0]]
    for p in raw[1:]:
        delta = p - out[-1]
        while delta > 180.0:
            delta -= 360.0
        while delta < -180.0:
            delta += 360.0
        out.append(out[-1] + delta)
    return out


def ac_calc(data):
    freq = data.get("ac_freq") or []
    vout = data.get("ac_vout") or []
    if not freq or not vout:
        raise RuntimeError("AC data missing freq/vout")
    mags_db = [20.0 * math.log10(max(abs(v), 1e-30)) for v in vout]
    phase = unwrap_phase(vout)
    adc = mags_db[0]
    cross = None
    for i in range(1, len(mags_db)):
        if mags_db[i - 1] >= 0.0 > mags_db[i]:
            alpha = (0.0 - mags_db[i - 1]) / (mags_db[i] - mags_db[i - 1])
            gbw_hz = freq[i - 1] + alpha * (freq[i] - freq[i - 1])
            phase_at = phase[i - 1] + alpha * (phase[i] - phase[i - 1])
            pm = phase_at
            if pm < 0.0:
                pm += 180.0
            if pm > 180.0:
                pm -= 180.0
            cross = {
                "i0": i - 1,
                "i1": i,
                "alpha": alpha,
                "f0": freq[i - 1],
                "f1": freq[i],
                "mag0": mags_db[i - 1],
                "mag1": mags_db[i],
                "phase0": phase[i - 1],
                "phase1": phase[i],
                "gbw_hz": gbw_hz,
                "phase_at": phase_at,
                "pm": pm,
            }
            break
    if cross is None:
        raise RuntimeError("No 0 dB crossing found")
    return {
        "Adc_dB": adc,
        "GBW_MHz": cross["gbw_hz"] / 1e6,
        "PM_deg": cross["pm"],
        "phase_at_GBW_deg": cross["phase_at"],
        "first_freq": freq[0],
        "first_vout": vout[0],
        "first_abs": abs(vout[0]),
        "cross": cross,
    }


def idc_calc(data):
    val = data.get("dc_VDD:p")
    if val is None:
        val = data.get("dc_V0:p")
    if val is None:
        raise RuntimeError("Cannot find DC supply current VDD:p")
    return val, abs(val) * 1e6


def best_slope(time, vout, t_lo, t_hi, sign):
    best = None
    for i in range(1, len(time)):
        if time[i] < t_lo or time[i - 1] > t_hi:
            continue
        dt = time[i] - time[i - 1]
        if dt <= 0:
            continue
        slope = (vout[i] - vout[i - 1]) / dt / 1e6
        if best is None:
            best = (slope, i - 1, i)
        elif sign > 0 and slope > best[0]:
            best = (slope, i - 1, i)
        elif sign < 0 and slope < best[0]:
            best = (slope, i - 1, i)
    if best is None:
        raise RuntimeError("No slope samples in window")
    slope, i0, i1 = best
    return {
        "slope": slope,
        "i0": i0,
        "i1": i1,
        "t0": time[i0],
        "t1": time[i1],
        "v0": vout[i0],
        "v1": vout[i1],
    }


def tran_calc(data):
    time = data.get("time") or []
    vout = data.get("vout") or []
    if not time or not vout:
        raise RuntimeError("Transient data missing time/vout")
    pos = best_slope(time, vout, 55e-9, 250e-9, 1)
    neg = best_slope(time, vout, 1.055e-6, 1.25e-6, -1)
    return {
        "SR_pos_V_us": pos["slope"],
        "SR_neg_V_us": abs(neg["slope"]),
        "pos": pos,
        "neg": neg,
    }


def print_calculation(name, ac, idc_raw, idc_ua, tran):
    c = ac["cross"]
    print("  [calc] Adc")
    print(
        "         first AC sample: f=%s, vout=(%.6g%+.6gj), |A|=%.6g"
        % (fmt_si(ac["first_freq"], "Hz"), ac["first_vout"].real, ac["first_vout"].imag, ac["first_abs"])
    )
    print("         Adc = 20*log10(|A|) = %.4f dB" % ac["Adc_dB"])
    print("  [calc] GBW / PM")
    print(
        "         unity bracket: f0=%s mag0=%.4f dB phase0=%.4f deg"
        % (fmt_si(c["f0"], "Hz"), c["mag0"], c["phase0"])
    )
    print(
        "                        f1=%s mag1=%.4f dB phase1=%.4f deg"
        % (fmt_si(c["f1"], "Hz"), c["mag1"], c["phase1"])
    )
    print("         alpha=(0-mag0)/(mag1-mag0)=%.6f" % c["alpha"])
    print("         GBW=f0+alpha*(f1-f0)=%.6f MHz" % ac["GBW_MHz"])
    print("         phase@GBW=phase0+alpha*(phase1-phase0)=%.4f deg" % ac["phase_at_GBW_deg"])
    print("         PM=phase@GBW+180deg when phase is negative = %.4f deg" % ac["PM_deg"])
    print("  [calc] Idc")
    print("         dcOp supply branch current VDD:p = %.8e A" % idc_raw)
    print("         Idc = abs(VDD:p)*1e6 = %.4f uA" % idc_ua)
    print("  [calc] Slew rate")
    p = tran["pos"]
    n = tran["neg"]
    print("         SR+ window: 55ns..250ns, max adjacent slope:")
    print(
        "         (%s, %s) -> (%s, %s)"
        % (fmt_si(p["t0"], "s"), fmt_si(p["v0"], "V"), fmt_si(p["t1"], "s"), fmt_si(p["v1"], "V"))
    )
    print("         SR+ = (v1-v0)/(t1-t0)/1e6 = %.4f V/us" % tran["SR_pos_V_us"])
    print("         SR- window: 1.055us..1.25us, most negative adjacent slope:")
    print(
        "         (%s, %s) -> (%s, %s)"
        % (fmt_si(n["t0"], "s"), fmt_si(n["v0"], "V"), fmt_si(n["t1"], "s"), fmt_si(n["v1"], "V"))
    )
    print("         SR- = abs((v1-v0)/(t1-t0)/1e6) = %.4f V/us" % tran["SR_neg_V_us"])


def append_waveform_points(point_rows, variant, ac_data, tran_data):
    freq = ac_data.get("ac_freq") or []
    vout_ac = ac_data.get("ac_vout") or []
    phase = unwrap_phase(vout_ac)
    for i, f in enumerate(freq):
        v = vout_ac[i] if i < len(vout_ac) else complex(float("nan"), float("nan"))
        mag = abs(v)
        point_rows.append(
            {
                "variant": variant,
                "analysis": "ac",
                "index": i,
                "x_name": "freq",
                "x_value": f,
                "x_unit": "Hz",
                "vout_real": v.real,
                "vout_imag": v.imag,
                "vout_abs": mag,
                "vout_mag_dB": 20.0 * math.log10(max(mag, 1e-30)),
                "vout_phase_deg": phase[i] if i < len(phase) else "",
                "vstim_V": "",
                "vout_V": "",
                "supply_current_A": "",
                "slope_from_prev_V_us": "",
            }
        )

    time = tran_data.get("time") or []
    vout_tran = tran_data.get("vout") or []
    vstim = tran_data.get("vstim") or []
    supply = tran_data.get("VDD:p") or tran_data.get("V0:p") or []
    prev_t = None
    prev_v = None
    for i, t in enumerate(time):
        v = vout_tran[i] if i < len(vout_tran) else float("nan")
        slope = ""
        if prev_t is not None and t > prev_t:
            slope = (v - prev_v) / (t - prev_t) / 1e6
        point_rows.append(
            {
                "variant": variant,
                "analysis": "tran",
                "index": i,
                "x_name": "time",
                "x_value": t,
                "x_unit": "s",
                "vout_real": "",
                "vout_imag": "",
                "vout_abs": "",
                "vout_mag_dB": "",
                "vout_phase_deg": "",
                "vstim_V": vstim[i] if i < len(vstim) else "",
                "vout_V": v,
                "supply_current_A": supply[i] if i < len(supply) else "",
                "slope_from_prev_V_us": slope,
            }
        )
        prev_t = t
        prev_v = v

    for key in ("dc_VDD:p", "dc_V0:p"):
        if key in ac_data:
            point_rows.append(
                {
                    "variant": variant,
                    "analysis": "dcOp",
                    "index": 0,
                    "x_name": "dcOp",
                    "x_value": 0,
                    "x_unit": "",
                    "vout_real": "",
                    "vout_imag": "",
                    "vout_abs": "",
                    "vout_mag_dB": "",
                    "vout_phase_deg": "",
                    "vstim_V": "",
                    "vout_V": ac_data.get("dc_vout", ""),
                    "supply_current_A": ac_data[key],
                    "slope_from_prev_V_us": "",
                }
            )
            break


def run_variant(variant, run_dir, point_rows):
    print("\n================================================================")
    print("[%s] %s" % (variant, VARIANTS[variant]["title"]))
    print("================================================================")
    include_file = prepare_include(variant, run_dir)
    tb_ac = write_tb_ac(variant, include_file, run_dir)
    tb_tran = write_tb_tran(variant, include_file, run_dir)
    print("  input include: %s" % VARIANTS[variant]["include"])
    print("  generated AC tb: %s" % tb_ac)
    print("  generated TRAN tb: %s" % tb_tran)
    raw_ac = run_spectre(tb_ac, run_dir)
    raw_tran = run_spectre(tb_tran, run_dir)
    ac_data = parse_raw_dir(raw_ac)
    tran_data = parse_raw_dir(raw_tran)
    ac = ac_calc(ac_data)
    idc_raw, idc_ua = idc_calc(ac_data)
    tran = tran_calc(tran_data)
    append_waveform_points(point_rows, variant, ac_data, tran_data)
    print_calculation(variant, ac, idc_raw, idc_ua, tran)
    row = {
        "variant": variant,
        "Adc_dB": ac["Adc_dB"],
        "GBW_MHz": ac["GBW_MHz"],
        "PM_deg": ac["PM_deg"],
        "phase_at_GBW_deg": ac["phase_at_GBW_deg"],
        "Idc_uA": idc_ua,
        "SR_pos_V_us": tran["SR_pos_V_us"],
        "SR_neg_V_us": tran["SR_neg_V_us"],
        "run_dir": str(run_dir),
    }
    passed = sum(1 for key, _label, _spec, check in SPEC if check(row[key]))
    print("  [result] %s: %d/6 pass" % (variant, passed))
    return row


def print_status_checks():
    print("\n================================================================")
    print("[verification files] DRC/LVS/PEX current report check")
    print("================================================================")
    drc = REPORTS.get("drc")
    lvs = REPORTS.get("lvs")
    pex_log = REPORTS.get("pex_log")
    lvs_cell = REPORTS.get("lvs_cell") or VARIANTS.get("pex_rc", {}).get("cell", "")
    print("  Fixed source paths used by this script:")
    print("    model(tt): %s" % MODEL)
    print("    pre-sim schematic netlist: %s" % VARIANTS["schematic_ref"]["include"])
    print("    PEX no-R/C netlist: %s" % VARIANTS["pex_norc"]["include"])
    print("    PEX full R+C netlist: %s" % VARIANTS["pex_rc"]["include"])
    for label, path in [("DRC", drc), ("LVS", lvs), ("PEX log", pex_log)]:
        if path:
            print("  %s: %s" % (label, path))
    if drc and drc.exists():
        for line in drc.read_text(errors="replace").splitlines():
            if "TOTAL DRC Results Generated" in line:
                print("  DRC summary: %s" % line.strip())
    if lvs and lvs.exists():
        for line in lvs.read_text(errors="replace").splitlines():
            if re.search(r"\bCORRECT\b.*%s" % re.escape(lvs_cell), line):
                print("  LVS summary: %s" % line.strip())
                break
    if pex_log and pex_log.exists():
        matches = [
            ln.strip()
            for ln in pex_log.read_text(errors="replace").splitlines()
            if "xRC Warnings" in ln or "xRC Errors" in ln or "LVS completed. CORRECT" in ln
        ]
        for ln in matches[-5:]:
            print("  PEX summary: %s" % ln)
    if not any((drc, lvs, pex_log)):
        print("  No report paths configured; skipping DRC/LVS/PEX summary.")
    print("  Note: report summaries are read from configured Calibre work directories.")
    print("        Performance metrics below are not read from old CSV/raw files; Spectre is re-run into a new run directory.")


def print_summary(rows, csv_path, points_path):
    print("\n================================================================")
    print("Final 6-metric summary")
    print("================================================================")
    headers = ["variant"] + [label for _key, label, _spec, _check in SPEC] + ["pass"]
    print("{:<16} {:>10} {:>10} {:>10} {:>10} {:>10} {:>10} {:>8}".format(*headers))
    for row in rows:
        pass_count = sum(1 for key, _label, _spec, check in SPEC if check(row[key]))
        print(
            "{:<16} {:>10.2f} {:>10.2f} {:>10.2f} {:>10.2f} {:>10.2f} {:>10.2f} {:>8}".format(
                row["variant"],
                row["Adc_dB"],
                row["GBW_MHz"],
                row["PM_deg"],
                row["Idc_uA"],
                row["SR_pos_V_us"],
                row["SR_neg_V_us"],
                "%d/6" % pass_count,
            )
        )
    print("\nSpec:")
    for key, label, spec, _check in SPEC:
        print("  %s: %s" % (label, spec))
    print("\nFresh metrics CSV written to: %s" % csv_path)
    print("Fresh all-points CSV written to: %s" % points_path)
    print("\nProject: %s" % PROJECT_NAME)
    print("Source : %s" % PROJECT_REPO)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run OPA post-layout Spectre verification")
    parser.add_argument("--config", default=os.environ.get("OPA_VERIFY_CONFIG"), help="JSON config file")
    parser.add_argument(
        "--variants",
        default="schematic_ref,pex_norc,pex_rc",
        help="comma-separated variants: schematic_ref,pex_norc,pex_rc",
    )
    parser.add_argument("--model", help="Spectre model file")
    parser.add_argument("--spectre", help="Spectre executable, e.g. spectre or /path/to/spectre")
    parser.add_argument("--run-root", help="directory that will receive runs/run_YYYYMMDD-HHMMSS")
    parser.add_argument("--schematic-netlist", help="schematic reference input.scs")
    parser.add_argument("--pex-norc", help="PEX no-R/C Spectre netlist")
    parser.add_argument("--pex-rc", help="PEX full R+C Spectre netlist")
    parser.add_argument("--schematic-cell", help="schematic subckt/cell name")
    parser.add_argument("--pex-cell", help="PEX subckt/cell name")
    parser.add_argument("--no-report-check", action="store_true", help="skip DRC/LVS/PEX report summary")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    if args.config:
        apply_config(load_json_config(args.config))
    apply_cli_overrides(args)
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    for v in variants:
        if v not in VARIANTS:
            raise SystemExit("unknown variant %s; choices: %s" % (v, ",".join(sorted(VARIANTS))))
    if not executable_available(SPECTRE):
        raise SystemExit("spectre not found: %s" % SPECTRE)
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS / ("run_" + run_id)
    run_dir.mkdir(parents=True)
    print("================================================================")
    print("%s :: OPA post-layout Spectre verification" % PROJECT_NAME)
    print("source : %s" % PROJECT_REPO)
    print("author : %s" % PROJECT_AUTHOR)
    print("license: %s (%s)" % (PROJECT_LICENSE, PROJECT_COPYRIGHT))
    print("================================================================")
    print("OPA live verification run_id=%s" % run_id)
    print("host=%s cwd=%s" % (subprocess.check_output(["hostname"], universal_newlines=True).strip(), run_dir))
    print("model=%s section=tt temp=27C VDD=4V CL=2pF" % MODEL)
    if not args.no_report_check:
        print_status_checks()
    rows = []
    point_rows = []
    for variant in variants:
        rows.append(run_variant(variant, run_dir, point_rows))
    csv_path = run_dir / "opa_live_metrics.csv"
    points_path = run_dir / "all_waveform_points.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "variant",
                "Adc_dB",
                "GBW_MHz",
                "PM_deg",
                "phase_at_GBW_deg",
                "Idc_uA",
                "SR_pos_V_us",
                "SR_neg_V_us",
                "run_dir",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    with points_path.open("w", newline="") as f:
        fields = [
            "variant",
            "analysis",
            "index",
            "x_name",
            "x_value",
            "x_unit",
            "vout_real",
            "vout_imag",
            "vout_abs",
            "vout_mag_dB",
            "vout_phase_deg",
            "vstim_V",
            "vout_V",
            "supply_current_A",
            "slope_from_prev_V_us",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(point_rows)
    print_summary(rows, csv_path, points_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
