"""SpectreRunner: run standalone Spectre netlists on the remote host.

Independent of the SKILL bridge — it only needs SSH access and a `spectre`
binary reachable on the remote shell (optionally via a csh env script). Useful
for the "bypass maestro, drive raw netlists" workflow.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .config import Settings, load_env, _get
from .ssh import CmdResult, SshSession


@dataclass
class SpectreRunner:
    settings: Settings
    ssh: SshSession = field(default=None)  # type: ignore
    spectre_bin: str = "spectre"
    cadence_cshrc: str | None = None

    def __post_init__(self):
        if self.ssh is None:
            self.ssh = SshSession(self.settings)

    @classmethod
    def from_env(cls, profile: str | None = None, env_path=None) -> "SpectreRunner":
        s = Settings.from_env(profile=profile, env_path=env_path)
        load_env(env_path)
        return cls(
            settings=s,
            spectre_bin=_get("SPECTRE_BIN", profile) or "spectre",
            cadence_cshrc=_get("CADENCE_CSHRC", profile),
        )

    # -- command assembly -------------------------------------------------
    def _wrap(self, inner: str) -> str:
        """Wrap a shell command so the Cadence env is available."""
        if self.cadence_cshrc:
            return "csh -c %s" % shlex.quote("source %s; %s" % (self.cadence_cshrc, inner))
        return "bash -lc %s" % shlex.quote(inner)

    def check(self) -> bool:
        r = self.ssh.run(self._wrap("which %s" % self.spectre_bin), timeout=30)
        return r.ok and bool(r.out.strip())

    # -- run --------------------------------------------------------------
    def run_netlist(self, netlist_text: str, run_name: str, args: str = "+aps",
                    timeout: float = 600.0) -> CmdResult:
        """Upload a netlist, run Spectre, and leave results in a remote run dir."""
        workdir = str(PurePosixPath(self.settings.scratch_root) / "spectre_runs" / run_name)
        netlist = str(PurePosixPath(workdir) / "input.scs")
        rawdir = str(PurePosixPath(workdir) / "psf")
        self.ssh.write_remote_text(netlist_text, netlist)
        cmd = "cd %s && %s %s -format psfascii -raw %s %s" % (
            shlex.quote(workdir), shlex.quote(self.spectre_bin), shlex.quote(netlist),
            shlex.quote(rawdir), args)
        return self.ssh.run(self._wrap(cmd), timeout=timeout)

    def fetch(self, remote_path: str, local_path: str) -> CmdResult:
        return self.ssh.download(remote_path, local_path)


# -- minimal PSF ASCII reader ------------------------------------------------
def parse_psf_ascii(text: str) -> dict:
    """Parse the VALUE section of a PSF-ASCII file into {signal: [values...]}.

    Handles the common DC/AC/transient ASCII layout. Real (and complex, written
    as two numbers) values are returned as floats / (re, im) tuples. This is a
    pragmatic reader for quick scripting; for heavy use prefer the dedicated
    parsing in tools/postlayout-verify.
    """
    out: dict[str, list] = {}
    in_value = False
    num = re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?")
    for line in text.splitlines():
        s = line.strip()
        if s == "VALUE":
            in_value = True
            continue
        if s == "END":
            in_value = False
            continue
        if not in_value or not s:
            continue
        m = re.match(r'"([^"]+)"\s+(.*)', s)
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        vals = [float(x) for x in num.findall(rest)]
        if not vals:
            continue
        out.setdefault(name, []).append(vals[0] if len(vals) == 1 else tuple(vals))
    return out
