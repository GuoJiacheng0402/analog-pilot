"""`apilot` command-line interface.

Subcommands: init, start, status, stop, restart.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings, load_env, _default_env_path
from .skill import SkillClient

ENV_TEMPLATE = """# AnalogPilot connection config. Fill in the placeholders; never commit this file.
APILOT_REMOTE_HOST={host}
APILOT_REMOTE_USER={user}

# Campus servers: disabling SSH ControlMaster avoids an empty-probe failure.
APILOT_DISABLE_CONTROL_MASTER=true

# Keep deployed bridge files in your home dir (not /tmp, which is cleared on reboot).
APILOT_REMOTE_SCRATCH_ROOT=/SM01/home/<grade>/{user}/.apilot

# Ports are auto-assigned from your username; override only if needed.
# APILOT_REMOTE_PORT=
# APILOT_LOCAL_PORT=

# Spectre standalone channel (optional): a csh-syntax env script that puts
# `spectre` on PATH. Leave unset for pure SKILL use.
# APILOT_CADENCE_CSHRC=/SM01/home/<grade>/{user}/.apilot_cadence.csh
"""


def cmd_init(args) -> int:
    path = Path(args.env).expanduser() if args.env else _default_env_path()
    if path.exists() and not args.force:
        print("%s already exists (use --force to overwrite)" % path)
        return 0
    host, user = "<EDA_SERVER_IP>", "<YOUR_STUDENT_ID>"
    if args.target:
        if "@" in args.target:
            user, host = args.target.split("@", 1)
        else:
            host = args.target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ENV_TEMPLATE.format(host=host, user=user), encoding="utf-8")
    print("wrote %s" % path)
    print("Edit it, then run: apilot start")
    return 0


def cmd_start(args) -> int:
    client = SkillClient.from_env(profile=args.profile)
    if not client.ssh.check():
        print("[ssh] cannot reach %s — fix passwordless SSH first "
              "(ssh-copy-id %s)" % (client.s.remote_host, client.s.ssh_target))
        return 1
    print("[ssh] %s reachable" % client.s.remote_host)
    line = client.start()
    print("[tunnel] localhost:%d -> %s:%d" % (client.s.local_port, client.s.remote_host, client.s.remote_port))
    print("\nPaste this line into the Virtuoso CIW (once per Virtuoso start):\n")
    print("    %s\n" % line)
    print("Tip: add the snippet from docs/templates/cdsinit_autoload.il to ~/.cdsinit to auto-load.")
    print("Then verify with: apilot status")
    return 0


def cmd_status(args) -> int:
    client = SkillClient.from_env(profile=args.profile)
    st = client.status()
    print("[tunnel]  %s" % st["tunnel"])
    print("[daemon]  %s" % st["daemon"])
    if st["daemon"] == "NO RESPONSE":
        print("          -> check the VNC desktop for an unclosed Virtuoso dialog,")
        print("             and confirm you pasted the load(\"...\") line in the CIW.")
    return 0 if st["daemon"] == "OK" else 1


def cmd_stop(args) -> int:
    client = SkillClient.from_env(profile=args.profile)
    client.stop()
    print("[tunnel] stopped")
    return 0


def cmd_selftest(args) -> int:
    from .spectre import SpectreRunner

    def mark(ok):
        return "ok" if ok else "--"

    client = SkillClient.from_env(profile=args.profile)
    print("AnalogPilot self-test (profile=%s)" % (args.profile or "default"))
    ssh_ok = client.ssh.check()
    print("  [%s] ssh reachable      : %s" % (mark(ssh_ok), client.s.remote_host))
    st = client.status()
    print("  [%s] tunnel             : %s" % (mark(st["tunnel"] == "running"), st["tunnel"]))
    print("  [%s] daemon             : %s" % (mark(st["daemon"] == "OK"), st["daemon"]))
    skill_ok = False
    if st["daemon"] == "OK":
        r = client.execute("1+2")
        skill_ok = r.ok and r.output.strip() == "3"
        print("  [%s] SKILL execute(1+2) : %s" % (mark(skill_ok), r.output))
    try:
        sp = SpectreRunner.from_env(profile=args.profile).check()
        print("  [%s] spectre channel    : %s"
              % (mark(sp), "found" if sp else "not configured (set APILOT_CADENCE_CSHRC)"))
    except Exception as exc:  # noqa: BLE001
        print("  [--] spectre channel    : %r" % exc)
    if not (ssh_ok and skill_ok):
        print("\nIf daemon is not OK: run `apilot start` and paste the load(\"...\") line in the CIW;")
        print("also check the VNC desktop for an unclosed Virtuoso dialog.")
    return 0 if (ssh_ok and skill_ok) else 1


def cmd_restart(args) -> int:
    cmd_stop(args)
    return cmd_start(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apilot", description="AnalogPilot bridge CLI")
    p.add_argument("-p", "--profile", default=None, help="profile suffix (e.g. lab2)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="write a .env template")
    pi.add_argument("target", nargs="?", help="[user@]host to prefill")
    pi.add_argument("--env", help="path to write (default ~/.apilot/.env)")
    pi.add_argument("--force", action="store_true")
    pi.set_defaults(func=cmd_init)

    for name, fn, help_ in [
        ("start", cmd_start, "open tunnel + deploy daemon"),
        ("status", cmd_status, "check tunnel + daemon"),
        ("selftest", cmd_selftest, "check the whole chain: ssh, tunnel, daemon, SKILL, spectre"),
        ("stop", cmd_stop, "stop the tunnel"),
        ("restart", cmd_restart, "stop then start"),
    ]:
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(func=fn)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
