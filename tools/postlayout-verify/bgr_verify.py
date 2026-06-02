#!/usr/bin/env python3
# Copyright (c) 2026 GuoJiacheng and the analog-pilot contributors.
# Licensed under the GNU GPL v3.0 with an additional attribution term (GPL-3.0 Section 7(b)). See LICENSE.
"""BGR post-layout verification driver.

Project : analog-pilot
Author  : GuoJiacheng
Source  : https://github.com/GuoJiacheng0402/analog-pilot
License : GPL-3.0-only with a Section 7(b) attribution term (see LICENSE and NOTICE)

Intended host: a Linux EDA server with Cadence Spectre, Mentor Calibre, and
the analog PDK installed. A typical invocation is:

    ./run_bgr_verify.sh --config ../configs/bgr.example.json

The script first reports the configured DRC/LVS/PEX source paths, optionally
re-runs Calibre PEX for the selected variant, and then runs a parallel
Spectre startup-transient temperature sweep on the current PEX netlist.
Outputs are a compact metrics CSV, a per-temperature CSV, and a long CSV
with every saved transient waveform sample.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_NAME = "analog-pilot"
PROJECT_REPO = "https://github.com/GuoJiacheng0402/analog-pilot"
PROJECT_AUTHOR = "GuoJiacheng"
PROJECT_LICENSE = "GPL-3.0-only"
PROJECT_COPYRIGHT = "Copyright 2026 GuoJiacheng"


def _path(value):
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


BASE = _path(os.environ.get("BGR_VERIFY_BASE", "~"))
CELL = os.environ.get("BGR_CELL", "bgr_postlayout")
MODEL = _path("~/Design/CSMC05_M3/Model/s05mixdtssa01v12.scs")
DRC_SUMMARY = BASE / ("work_bgr_drc_%s/result.summary" % CELL)
LVS_REPORT = BASE / ("work_bgr_lvs_%s/lvs.rep" % CELL)
GDS = BASE / ("work_bgr_drc_%s/%s.gds" % (CELL, CELL))
CDL = BASE / ("work_bgr_lvs_%s/%s.cdl" % (CELL, CELL))
PEX_NORC = BASE / ("work_bgr_pex_no-rc_%s/%s.norc.simple.scs" % (CELL, CELL))
PEX_NORC_LOG = BASE / ("work_bgr_pex_no-rc_%s/gui_batch.log" % CELL)
PEX_NORC_FMT_LOG = BASE / ("work_bgr_pex_no-rc_%s/xrc_fmt_simple.log" % CELL)
PEX_RC = BASE / ("work_bgr_pex_r-plus-c_%s/%s.pex.netlist" % (CELL, CELL))
PEX_RC_LOG = BASE / ("work_bgr_pex_r-plus-c_%s/gui_batch.log" % CELL)
PEX_DECK = BASE / "Calibre/pex/csmccalibre.xrc.t3"
COURSE_GUI_RUNSET = BASE / "course_digitalic/calibre/pex.runset"

CALIBRE_HOME = os.environ.get("CALIBRE_HOME", "")
MGLS_LICENSE_FILE = os.environ.get("MGLS_LICENSE_FILE", "")
SPECTRE = Path(os.environ.get("SPECTRE_BIN", "spectre"))
ROOT = _path(os.environ.get("BGR_VERIFY_RUN_ROOT", "~/bgr_verify"))
RUNS = ROOT / "runs"
CADENCE_HOME = os.environ.get("CADENCE_HOME", "")
MMSIMHOME = os.environ.get("MMSIMHOME", "")
CDS_LIC_FILE = os.environ.get("CDS_LIC_FILE", "")
VERIFY_LD_PRELOAD = os.environ.get("VERIFY_LD_PRELOAD", "")


VARIANTS = {
    "pex_rc": {
        "title": "PEX full R+C: bgr_postlayout",
        "include": PEX_RC,
        "pex_mode": "r-plus-c",
    },
    "pex_norc": {
        "title": "PEX no-R/C SIMPLE: bgr_postlayout",
        "include": PEX_NORC,
        "pex_mode": "no-rc",
    },
}


def load_json_config(path):
    with _path(path).open() as f:
        return json.load(f)


def _recompute_default_paths():
    global DRC_SUMMARY, LVS_REPORT, GDS, CDL, PEX_NORC, PEX_NORC_LOG, PEX_NORC_FMT_LOG
    global PEX_RC, PEX_RC_LOG, PEX_DECK, COURSE_GUI_RUNSET
    DRC_SUMMARY = BASE / ("work_bgr_drc_%s/result.summary" % CELL)
    LVS_REPORT = BASE / ("work_bgr_lvs_%s/lvs.rep" % CELL)
    GDS = BASE / ("work_bgr_drc_%s/%s.gds" % (CELL, CELL))
    CDL = BASE / ("work_bgr_lvs_%s/%s.cdl" % (CELL, CELL))
    PEX_NORC = BASE / ("work_bgr_pex_no-rc_%s/%s.norc.simple.scs" % (CELL, CELL))
    PEX_NORC_LOG = BASE / ("work_bgr_pex_no-rc_%s/gui_batch.log" % CELL)
    PEX_NORC_FMT_LOG = BASE / ("work_bgr_pex_no-rc_%s/xrc_fmt_simple.log" % CELL)
    PEX_RC = BASE / ("work_bgr_pex_r-plus-c_%s/%s.pex.netlist" % (CELL, CELL))
    PEX_RC_LOG = BASE / ("work_bgr_pex_r-plus-c_%s/gui_batch.log" % CELL)
    PEX_DECK = BASE / "Calibre/pex/csmccalibre.xrc.t3"
    COURSE_GUI_RUNSET = BASE / "course_digitalic/calibre/pex.runset"
    VARIANTS["pex_rc"]["include"] = PEX_RC
    VARIANTS["pex_norc"]["include"] = PEX_NORC


def apply_config(config):
    global BASE, CELL, MODEL, SPECTRE, ROOT, RUNS, CALIBRE_HOME, MGLS_LICENSE_FILE
    global CADENCE_HOME, MMSIMHOME, CDS_LIC_FILE, VERIFY_LD_PRELOAD
    paths = config.get("paths", {})
    cadence = config.get("cadence", {})
    calibre = config.get("calibre", {})

    if "base" in paths:
        BASE = _path(paths["base"])
        _recompute_default_paths()
    if "cell" in config:
        CELL = config["cell"]
        _recompute_default_paths()
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
    CALIBRE_HOME = calibre.get("calibre_home", CALIBRE_HOME)
    MGLS_LICENSE_FILE = calibre.get("mgls_license_file", MGLS_LICENSE_FILE)

    path_keys = {
        "drc_summary": "DRC_SUMMARY",
        "lvs_report": "LVS_REPORT",
        "gds": "GDS",
        "cdl": "CDL",
        "pex_norc": "PEX_NORC",
        "pex_norc_log": "PEX_NORC_LOG",
        "pex_norc_fmt_log": "PEX_NORC_FMT_LOG",
        "pex_rc": "PEX_RC",
        "pex_rc_log": "PEX_RC_LOG",
        "pex_deck": "PEX_DECK",
        "course_gui_runset": "COURSE_GUI_RUNSET",
    }
    for key, global_name in path_keys.items():
        if key in paths:
            globals()[global_name] = _path(paths[key])
    VARIANTS["pex_rc"]["include"] = PEX_RC
    VARIANTS["pex_norc"]["include"] = PEX_NORC

    for name, patch in config.get("variants", {}).items():
        if name not in VARIANTS:
            raise SystemExit("config has unknown BGR variant %s" % name)
        for key in ("title", "pex_mode"):
            if key in patch:
                VARIANTS[name][key] = patch[key]
        if "include" in patch:
            VARIANTS[name]["include"] = _path(patch["include"])


def apply_cli_overrides(args):
    global CELL, MODEL, SPECTRE, ROOT, RUNS
    if args.cell:
        CELL = args.cell
        _recompute_default_paths()
    if args.model:
        MODEL = _path(args.model)
    if args.spectre:
        SPECTRE = _path(args.spectre)
    if args.run_root:
        ROOT = _path(args.run_root)
        RUNS = ROOT / "runs"
    if args.pex_norc:
        VARIANTS["pex_norc"]["include"] = _path(args.pex_norc)
    if args.pex_rc:
        VARIANTS["pex_rc"]["include"] = _path(args.pex_rc)


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


def calibre_env():
    env = os.environ.copy()
    hostname = subprocess.check_output(["hostname"], universal_newlines=True).strip()
    if CALIBRE_HOME:
        env["CALIBRE_HOME"] = CALIBRE_HOME
        env["PATH"] = str(Path(CALIBRE_HOME) / "bin") + ":" + env.get("PATH", "")
    if MGLS_LICENSE_FILE:
        env["MGLS_LICENSE_FILE"] = MGLS_LICENSE_FILE.format(hostname=hostname)
    return env


def read_text(path):
    return Path(path).read_text(errors="replace")


def sanitize_pex_for_spectre(text, source_path):
    source_path = Path(source_path)
    base = str(source_path.parent)
    cell = source_path.name
    pxi = "%s.%s.pxi" % (source_path.name, CELL)
    companions = (cell + ".pex", cell + "." + CELL + ".pxi", pxi)

    def fix_include(match):
        name = match.group(1)
        path = Path(name)
        if path.is_absolute():
            return 'include "%s"' % name
        if name in companions or name.startswith(source_path.name + "."):
            return 'include "%s/%s"' % (base, name)
        return match.group(0)

    text = re.sub(r'include\s+"([^"]+)"', fix_include, text)
    text = re.sub(r"\\\n[ \t]*\n", "\\\n", text)
    text = re.sub(r"(\)\s+)rhr1k\b", r"\1resistor", text)
    text = re.sub(r"(\)\s+)rpoly2\b", r"\1resistor", text)
    text = re.sub(r"(\)\s+)cpip\b", r"\1capacitor", text)
    text = re.sub(r"(?m)^(\s*)rhr1k\b", r"\1resistor", text)
    text = re.sub(r"(?m)^(\s*)rpoly2\b", r"\1resistor", text)
    text = re.sub(r"(?m)^(\s*)cpip\b", r"\1capacitor", text)
    return text


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
    for name in ("tran1.tran.tran", "tran1.tran", "tran.tran.tran", "tran.tran"):
        p = raw_dir / name
        if p.exists():
            merged.update(parse_psf_file(p))
            break
    return merged


def list_signal(data, names):
    lowered = {key.lower(): key for key in data}
    for name in names:
        key = lowered.get(name.lower())
        value = data.get(key) if key else None
        if isinstance(value, list):
            return [float(x) for x in value]
    for key, value in data.items():
        low = key.lower()
        if isinstance(value, list) and any(name.lower() in low for name in names):
            return [float(x) for x in value]
    raise RuntimeError("missing signal %s; keys=%s" % (names, sorted(data)[:50]))


def settled_stats(values, times, tail_window_s):
    if not values:
        raise RuntimeError("empty signal")
    if times and len(times) == len(values):
        cutoff = times[-1] - tail_window_s
        pairs = [(t, v) for t, v in zip(times, values) if t >= cutoff]
        if pairs:
            vals = [v for _t, v in pairs]
            return sum(vals) / len(vals), len(vals), pairs[0][0], pairs[-1][0]
    n_tail = max(5, len(values) // 10)
    vals = values[-n_tail:]
    return sum(vals) / len(vals), len(vals), None, None


def calc_tc(values, temp_span):
    avg = sum(values) / len(values)
    vmin = min(values)
    vmax = max(values)
    delta = vmax - vmin
    tc = delta / (avg * temp_span) * 1e6
    return avg, vmin, vmax, delta, tc


def tag_temp(temp_c):
    return str(temp_c).replace("-", "m").replace(".", "p")


def prepare_include(variant, run_dir):
    src = Path(VARIANTS[variant]["include"])
    if not src.exists():
        raise RuntimeError("missing PEX netlist: %s" % src)
    text = sanitize_pex_for_spectre(src.read_text(errors="replace"), src)
    dest = run_dir / ("%s_include.scs" % variant)
    dest.write_text(text)
    return dest


def write_tb(variant, include_file, temp_c, args, run_dir):
    tb = run_dir / ("tb_%s_t%s.scs" % (variant, tag_temp(temp_c)))
    tb.write_text(
        """simulator lang=spectre
global 0
include "%s" section=tt
include "%s" section=biptypical
include "%s"

// BGR subckt order from Calibre PEX: (VREF VSS VDD)
// Real startup: VDD ramps from 0V to %.8gV, no saved operating point is reused.
V_VDD (vdd 0) vsource type=pulse val0=0 val1=%.8g delay=0 rise=%.8g fall=%.8g width=200u period=400u
XBGR (vref 0 vdd) %s

tran1 tran stop=%.8g errpreset=moderate maxstep=%.8g annotate=status

save vref XBGR.vinx XBGR.viny XBGR.net2 V_VDD:p
simulatorOptions options reltol=1e-6 vabstol=1e-9 iabstol=1e-15 \\
    temp=%.8g tnom=25 gmin=1e-13 maxnotes=5 maxwarns=20 psfversion="1.4.0"
saveOptions options save=allpub
"""
        % (
            MODEL,
            MODEL,
            include_file,
            args.vdd,
            args.vdd,
            args.rise,
            args.rise,
            CELL,
            args.stop,
            args.maxstep,
            temp_c,
        )
    )
    return tb


def run_spectre(tb, work_dir):
    raw = work_dir / (tb.stem + ".raw")
    log = work_dir / (tb.stem + ".log")
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
    proc = subprocess.run(
        cmd,
        cwd=str(work_dir),
        env=spectre_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("Spectre failed for %s:\n%s" % (tb, proc.stdout[-4000:]))
    return raw


def run_temp_point(variant, include_file, temp_c, args, run_dir):
    point_dir = run_dir / ("%s_t%s" % (variant, tag_temp(temp_c)))
    point_dir.mkdir(parents=True, exist_ok=True)
    tb = write_tb(variant, include_file, temp_c, args, point_dir)
    raw = run_spectre(tb, point_dir)
    data = parse_raw_dir(raw)
    times = list_signal(data, ("time", "tran1_time"))
    vref = list_signal(data, ("vref", "tran1_vref"))
    vinx = list_signal(data, ("XBGR.vinx", "vinx"))
    viny = list_signal(data, ("XBGR.viny", "viny"))
    net2 = list_signal(data, ("XBGR.net2", "net2"))
    try:
        ivdd = [-x for x in list_signal(data, ("V_VDD:p",))]
    except RuntimeError:
        ivdd = [float("nan")] * len(times)

    vref_avg, tail_n, tail_t0, tail_t1 = settled_stats(vref, times, args.tail)
    vinx_avg, _n, _t0, _t1 = settled_stats(vinx, times, args.tail)
    viny_avg, _n, _t0, _t1 = settled_stats(viny, times, args.tail)
    net2_avg, _n, _t0, _t1 = settled_stats(net2, times, args.tail)
    ivdd_avg, _n, _t0, _t1 = settled_stats(ivdd, times, args.tail)

    temp_row = {
        "variant": variant,
        "temp_c": temp_c,
        "vref_v": vref_avg,
        "vinx_v": vinx_avg,
        "viny_v": viny_avg,
        "net2_v": net2_avg,
        "ivdd_uA": ivdd_avg * 1e6,
        "tail_sample_count": tail_n,
        "tail_start_s": tail_t0 if tail_t0 is not None else "",
        "tail_stop_s": tail_t1 if tail_t1 is not None else "",
        "tb": str(tb),
        "raw": str(raw),
    }
    wave_rows = []
    cutoff = times[-1] - args.tail if times else None
    n = min(len(times), len(vref), len(vinx), len(viny), len(net2), len(ivdd))
    for i in range(n):
        wave_rows.append(
            {
                "variant": variant,
                "temp_c": temp_c,
                "analysis": "tran",
                "index": i,
                "time_s": times[i],
                "vref_v": vref[i],
                "vinx_v": vinx[i],
                "viny_v": viny[i],
                "net2_v": net2[i],
                "ivdd_A": ivdd[i],
                "is_tail_sample": 1 if cutoff is not None and times[i] >= cutoff else 0,
            }
        )
    return temp_row, wave_rows


def run_variant(variant, args, run_dir):
    print("\n================================================================")
    print("[%s] %s" % (variant, VARIANTS[variant]["title"]))
    print("================================================================")
    include_file = prepare_include(variant, run_dir)
    temps = []
    t = args.temp_start
    while t <= args.temp_stop + 1e-9:
        temps.append(float(t))
        t += args.temp_step
    print("  input PEX netlist: %s" % VARIANTS[variant]["include"])
    print("  sanitized include: %s" % include_file)
    print("  temperatures: %.1fC..%.1fC step %.1fC (%d points)" % (temps[0], temps[-1], args.temp_step, len(temps)))
    print("  startup: VDD 0 -> %.3gV rise=%.3gs stop=%.3gs tail_avg=%.3gs" % (args.vdd, args.rise, args.stop, args.tail))

    temp_rows = []
    wave_rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {
            pool.submit(run_temp_point, variant, include_file, temp_c, args, run_dir): temp_c
            for temp_c in temps
        }
        for fut in as_completed(future_map):
            temp_c = future_map[fut]
            row, points = fut.result()
            temp_rows.append(row)
            wave_rows.extend(points)
            print(
                "  t=%6.1fC  Vref=%.6fV  Vinx=%.6fV  Viny=%.6fV  Net2=%.6fV  Idd=%.3fuA"
                % (temp_c, row["vref_v"], row["vinx_v"], row["viny_v"], row["net2_v"], row["ivdd_uA"])
            )
    temp_rows.sort(key=lambda r: r["temp_c"])
    vrefs = [r["vref_v"] for r in temp_rows]
    temp_span = args.temp_stop - args.temp_start
    avg, vmin, vmax, delta, tc = calc_tc(vrefs, temp_span)
    pass_tc = tc < args.tc_limit
    print("  [calc] TC")
    print("         avg(Vref) = sum(Vref_i)/N = %.9f V" % avg)
    print("         min(Vref) = %.9f V, max(Vref) = %.9f V" % (vmin, vmax))
    print("         delta = max - min = %.9f V" % delta)
    print("         TC = delta / (avg * %.1fC) * 1e6 = %.6f ppm/C" % (temp_span, tc))
    print("  [result] %s: %s (limit < %.3f ppm/C)" % (variant, "PASS" if pass_tc else "FAIL", args.tc_limit))
    metric_row = {
        "variant": variant,
        "points": len(temp_rows),
        "avg_vref_v": avg,
        "min_vref_v": vmin,
        "max_vref_v": vmax,
        "delta_vref_v": delta,
        "temp_start_c": args.temp_start,
        "temp_stop_c": args.temp_stop,
        "tc_ppm_per_c": tc,
        "tc_limit_ppm_per_c": args.tc_limit,
        "pass": "PASS" if pass_tc else "FAIL",
        "run_dir": str(run_dir),
    }
    return metric_row, temp_rows, wave_rows


def print_status_checks():
    print("\n================================================================")
    print("[verification files] DRC/LVS/PEX current report check")
    print("================================================================")
    print("  Fixed source paths used by this script:")
    print("    model(tt/bip): %s" % MODEL)
    print("    BGR GDS:       %s" % GDS)
    print("    source CDL:    %s" % CDL)
    print("    PEX no-R/C:    %s" % PEX_NORC)
    print("    PEX full R+C:  %s" % PEX_RC)
    print("    DRC report:    %s" % DRC_SUMMARY)
    print("    LVS report:    %s" % LVS_REPORT)
    print("    PEX no-R/C log:%s" % PEX_NORC_LOG)
    print("    PEX R+C log:   %s" % PEX_RC_LOG)
    if DRC_SUMMARY.exists():
        for line in read_text(DRC_SUMMARY).splitlines():
            if "TOTAL DRC Results Generated" in line:
                print("  DRC summary: %s" % line.strip())
    if LVS_REPORT.exists():
        for line in read_text(LVS_REPORT).splitlines():
            if re.search(r"\bCORRECT\b.*%s" % CELL, line):
                print("  LVS summary: %s" % line.strip())
                break
    for label, path in [("PEX no-R/C", PEX_NORC_LOG), ("PEX no-R/C SIMPLE", PEX_NORC_FMT_LOG), ("PEX full R+C", PEX_RC_LOG)]:
        if path.exists():
            text = read_text(path)
            matches = [
                ln.strip()
                for ln in text.splitlines()
                if "LVS completed. CORRECT" in ln
                or "xRC Warnings" in ln
                or "xRC Errors" in ln
                or "No ground net name defined" in ln
            ]
            print("  %s log: %s" % (label, path))
            for ln in matches[-5:]:
                print("    %s" % ln)
            if "No ground net name defined" not in text:
                print("    ground-net warning: absent")
    print("  Note: report summaries are read from fixed Calibre work dirs.")
    print("        TC metrics below are freshly re-simulated into a new run directory.")


def run_calibre_pex(mode):
    if mode == "no-rc":
        work = PEX_NORC.parent
        simple_netlist = PEX_NORC
        full_netlist = work / ("%s.pex.netlist" % CELL)
    else:
        work = PEX_RC.parent
        full_netlist = PEX_RC
        simple_netlist = work / ("%s.norc.simple.scs" % CELL)
    print("\n================================================================")
    print("[rerun-pex] Calibre GUI PEX mode=%s" % mode)
    print("================================================================")
    if work.exists():
        shutil.rmtree(str(work))
    work.mkdir(parents=True)
    (work / ("%s.gds" % CELL)).symlink_to(GDS)
    (work / ("%s.spice" % CELL)).symlink_to(CDL)
    keys = {
        "lvsRulesFile": str(BASE / "Calibre/lvs/calibre.xrc.lvs"),
        "lvsRunDir": str(work),
        "pexRulesFile": str(PEX_DECK),
        "pexRunDir": str(work),
        "pexLayoutPaths": str(work / ("%s.gds" % CELL)),
        "pexExtraLayoutPaths": "",
        "pexLayoutSystem": "GDSII",
        "pexLayoutPrimary": CELL,
        "pexLayoutLibrary": "ANALOG",
        "pexLayoutView": "layout",
        "pexLayoutGetFromViewer": "0",
        "pexSourcePath": str(work / ("%s.spice" % CELL)),
        "pexExtraSourcePaths": "",
        "pexSourceSystem": "SPICE",
        "pexSourcePrimary": CELL,
        "pexSourceLibrary": "ANALOG",
        "pexSourceView": "schematic",
        "pexSourceGetFromViewer": "0",
        "pexPexNetlistType": "RCC",
        "pexPexNetlistFile": str(full_netlist),
        "pexPexNetlistFormat": "SPECTRE",
        "pexReportFile": str(work / ("%s.lvs.report" % CELL)),
        "pexPexReportFile": str(work / ("%s.pex.report" % CELL)),
        "pexSVDBDir": str(work / "svdb"),
        "pexRunHierLVS": "1",
        "pexRunPHDBStep": "1",
        "pexRunPDBStep": "1",
        "pexRunFMTStep": "1",
        "pexPexExtractType": "T",
        "pexPexGroundName": "1",
        "pexPexGroundNameValue": "VSS",
        "pexGroundNames": "VSS",
        "pexPEXGroundNetNames": "VSS",
        "pexStartRVE": "0",
        "cmnStartRVEAfterBatch": "0",
        "cmnRunOnOpen": "0",
        "cmnPromptSaveRunset": "0",
        "cmnSaveRunsetOnRun": "0",
        "cmnDontWaitForLicense": "1",
    }
    lines = []
    for line in COURSE_GUI_RUNSET.read_text(errors="replace").splitlines():
        if line.startswith("*") and ":" in line:
            key = line[1:].split(":", 1)[0]
            if key in keys:
                line = "*%s: %s" % (key, keys[key])
        lines.append(line)
    (work / "pex_gui.runset").write_text("\n".join(lines) + "\n")
    cmd = ["calibre", "-gui", "-pex", "-runset", "pex_gui.runset", "-batch"]
    log = work / "gui_batch.log"
    with log.open("w") as f:
        proc = subprocess.run(cmd, cwd=str(work), env=calibre_env(), stdout=f, stderr=subprocess.STDOUT)
    print("  GUI_BATCH_RC=%s" % proc.returncode)
    text = read_text(log)
    for ln in [
        line.strip()
        for line in text.splitlines()
        if "LVS completed. CORRECT" in line or "xRC Warnings" in line or "xRC Errors" in line or "No ground net name defined" in line
    ][-8:]:
        print("  %s" % ln)
    if proc.returncode != 0:
        raise RuntimeError("Calibre PEX failed: %s" % log)
    if mode == "no-rc":
        src = work / "_csmccalibre.xrc.t3_"
        simple_deck = work / "_csmccalibre.norc.simple.t3_"
        out_lines = []
        inserted = False
        for line in src.read_text(errors="replace").splitlines():
            if line.startswith('PEX NETLIST "'):
                continue
            out_lines.append(line)
            if line.startswith("SOURCE PATH") and not inserted:
                out_lines.append('PEX NETLIST SIMPLE "%s" SPECTRE 1 SOURCENAMES SEPARATOR "/"' % simple_netlist)
                inserted = True
        simple_deck.write_text("\n".join(out_lines) + "\n")
        fmt_log = work / "xrc_fmt_simple.log"
        cmd = ["calibre", "-xrc", "-fmt", "-simple", "-64", str(simple_deck.name)]
        with fmt_log.open("w") as f:
            proc = subprocess.run(cmd, cwd=str(work), env=calibre_env(), stdout=f, stderr=subprocess.STDOUT)
        print("  FMT_SIMPLE_RC=%s" % proc.returncode)
        text = read_text(fmt_log)
        for ln in [
            line.strip()
            for line in text.splitlines()
            if "xRC Warnings" in line or "xRC Errors" in line or "No ground net name defined" in line or "OUTPUT NETLIST" in line
        ][-8:]:
            print("  %s" % ln)
        if proc.returncode != 0:
            raise RuntimeError("Calibre SIMPLE formatter failed: %s" % fmt_log)


def write_csvs(run_dir, metric_rows, temp_rows, wave_rows):
    metrics_csv = run_dir / "bgr_live_metrics.csv"
    temp_csv = run_dir / "temperature_points.csv"
    wave_csv = run_dir / "all_waveform_points.csv"
    with metrics_csv.open("w", newline="") as f:
        fields = [
            "variant",
            "points",
            "avg_vref_v",
            "min_vref_v",
            "max_vref_v",
            "delta_vref_v",
            "temp_start_c",
            "temp_stop_c",
            "tc_ppm_per_c",
            "tc_limit_ppm_per_c",
            "pass",
            "run_dir",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(metric_rows)
    with temp_csv.open("w", newline="") as f:
        fields = [
            "variant",
            "temp_c",
            "vref_v",
            "vinx_v",
            "viny_v",
            "net2_v",
            "ivdd_uA",
            "tail_sample_count",
            "tail_start_s",
            "tail_stop_s",
            "tb",
            "raw",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(temp_rows)
    with wave_csv.open("w", newline="") as f:
        fields = [
            "variant",
            "temp_c",
            "analysis",
            "index",
            "time_s",
            "vref_v",
            "vinx_v",
            "viny_v",
            "net2_v",
            "ivdd_A",
            "is_tail_sample",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(wave_rows)
    return metrics_csv, temp_csv, wave_csv


def print_summary(metric_rows, metrics_csv, temp_csv, wave_csv):
    print("\n================================================================")
    print("Final BGR TC summary")
    print("================================================================")
    print("{:<12} {:>8} {:>12} {:>12} {:>12} {:>12} {:>10}".format("variant", "points", "avg_vref", "delta_v", "TC ppm/C", "limit", "pass"))
    for row in metric_rows:
        print(
            "{:<12} {:>8} {:>12.6f} {:>12.6f} {:>12.6f} {:>12.3f} {:>10}".format(
                row["variant"],
                row["points"],
                row["avg_vref_v"],
                row["delta_vref_v"],
                row["tc_ppm_per_c"],
                row["tc_limit_ppm_per_c"],
                row["pass"],
            )
        )
    print("\nSpec:")
    print("  VDD = 4V")
    print("  Temperature = -40C..120C")
    print("  TC = delta(Vref) / (average(Vref) * delta(T)) * 1e6")
    print("  TC limit < 10 ppm/C")
    print("\nFresh metrics CSV written to: %s" % metrics_csv)
    print("Fresh temperature-points CSV written to: %s" % temp_csv)
    print("Fresh all-waveform-points CSV written to: %s" % wave_csv)
    print("\nProject: %s" % PROJECT_NAME)
    print("Source : %s" % PROJECT_REPO)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run BGR PEX startup TC verification")
    parser.add_argument("--config", default=os.environ.get("BGR_VERIFY_CONFIG"), help="JSON config file")
    parser.add_argument("--variants", default="pex_rc", help="comma-separated variants: pex_rc,pex_norc")
    parser.add_argument("--cell", help="BGR PEX subckt/cell name")
    parser.add_argument("--model", help="Spectre model file")
    parser.add_argument("--spectre", help="Spectre executable, e.g. spectre or /path/to/spectre")
    parser.add_argument("--run-root", help="directory that will receive runs/run_YYYYMMDD-HHMMSS")
    parser.add_argument("--pex-norc", help="PEX no-R/C Spectre netlist")
    parser.add_argument("--pex-rc", help="PEX full R+C Spectre netlist")
    parser.add_argument("--workers", type=int, default=4, help="parallel Spectre jobs")
    parser.add_argument("--temp-start", type=float, default=-40.0)
    parser.add_argument("--temp-stop", type=float, default=120.0)
    parser.add_argument("--temp-step", type=float, default=5.0)
    parser.add_argument("--vdd", type=float, default=4.0)
    parser.add_argument("--rise", type=float, default=2e-6)
    parser.add_argument("--stop", type=float, default=80e-6)
    parser.add_argument("--tail", type=float, default=10e-6)
    parser.add_argument("--maxstep", type=float, default=200e-9)
    parser.add_argument("--tc-limit", type=float, default=10.0)
    parser.add_argument("--no-report-check", action="store_true", help="skip DRC/LVS/PEX report summary")
    parser.add_argument("--no-sim", action="store_true", help="only print report summaries and create run directory")
    parser.add_argument("--rerun-pex", action="store_true", help="re-run Calibre PEX for selected variants before Spectre")
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
    print("%s :: BGR post-layout Spectre verification" % PROJECT_NAME)
    print("source : %s" % PROJECT_REPO)
    print("author : %s" % PROJECT_AUTHOR)
    print("license: %s (%s)" % (PROJECT_LICENSE, PROJECT_COPYRIGHT))
    print("================================================================")
    print("BGR PEX verification run_id=%s" % run_id)
    print("host=%s cwd=%s" % (subprocess.check_output(["hostname"], universal_newlines=True).strip(), run_dir))
    print("default final metric variant: pex_rc")
    if args.rerun_pex:
        modes = []
        for v in variants:
            mode = VARIANTS[v]["pex_mode"]
            if mode not in modes:
                modes.append(mode)
        for mode in modes:
            run_calibre_pex(mode)
    if not args.no_report_check:
        print_status_checks()
    if args.no_sim:
        return 0
    metric_rows = []
    temp_rows = []
    wave_rows = []
    for variant in variants:
        metric, temps, waves = run_variant(variant, args, run_dir)
        metric_rows.append(metric)
        temp_rows.extend(temps)
        wave_rows.extend(waves)
    metrics_csv, temp_csv, wave_csv = write_csvs(run_dir, metric_rows, temp_rows, wave_rows)
    print_summary(metric_rows, metrics_csv, temp_csv, wave_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
