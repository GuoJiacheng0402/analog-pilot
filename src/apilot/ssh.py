"""Thin SSH layer for AnalogPilot: command execution, file transfer, tunnel.

Wraps the system ``ssh``/``scp`` binaries (no third-party SSH library), so it
relies only on the user's existing key-based SSH access. Independently written.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass

from .config import Settings


@dataclass
class CmdResult:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class SshSession:
    """Run commands, transfer files, and open a port-forward to a host."""

    def __init__(self, settings: Settings):
        self.s = settings

    # -- base option list -------------------------------------------------
    def _base_opts(self) -> list[str]:
        opts = [
            "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=4",
        ]
        # On these campus servers ControlMaster multiplexing has been observed
        # to corrupt the remote interpreter probe, so default to disabling it.
        if self.s.disable_control_master:
            opts += ["-o", "ControlMaster=no", "-o", "ControlPath=none"]
        if self.s.jump_host:
            jump = "%s@%s" % (self.s.jump_user, self.s.jump_host) if self.s.jump_user else self.s.jump_host
            opts += ["-J", jump]
        return opts

    # -- remote command execution ----------------------------------------
    def run(self, command: str, timeout: float = 60.0) -> CmdResult:
        argv = ["ssh", *self._base_opts(), self.s.ssh_target, command]
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            return CmdResult(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return CmdResult(124, "", "ssh command timed out after %ss" % timeout)

    def check(self) -> bool:
        return self.run("echo apilot_ok", timeout=15).out.strip() == "apilot_ok"

    # -- file transfer ----------------------------------------------------
    def _scp_opts(self) -> list[str]:
        opts = ["-o", "BatchMode=yes"]
        if self.s.disable_control_master:
            opts += ["-o", "ControlMaster=no", "-o", "ControlPath=none"]
        if self.s.jump_host:
            jump = "%s@%s" % (self.s.jump_user, self.s.jump_host) if self.s.jump_user else self.s.jump_host
            opts += ["-J", jump]
        return opts

    def upload(self, local_path: str, remote_path: str, timeout: float = 120.0) -> CmdResult:
        argv = ["scp", *self._scp_opts(), local_path, "%s:%s" % (self.s.ssh_target, remote_path)]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return CmdResult(p.returncode, p.stdout, p.stderr)

    def download(self, remote_path: str, local_path: str, timeout: float = 120.0) -> CmdResult:
        argv = ["scp", *self._scp_opts(), "%s:%s" % (self.s.ssh_target, remote_path), local_path]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return CmdResult(p.returncode, p.stdout, p.stderr)

    def write_remote_text(self, text: str, remote_path: str, timeout: float = 60.0) -> CmdResult:
        """Write text to a remote file over ssh stdin (no temp file)."""
        cmd = 'mkdir -p "$(dirname %s)" && cat > %s' % (
            shlex.quote(remote_path), shlex.quote(remote_path))
        argv = ["ssh", *self._base_opts(), self.s.ssh_target, cmd]
        try:
            p = subprocess.run(argv, input=text, capture_output=True, text=True, timeout=timeout)
            return CmdResult(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return CmdResult(124, "", "ssh write timed out after %ss" % timeout)

    # -- TCP tunnel -------------------------------------------------------
    # The tunnel is a detached `ssh -f -N` so it survives a short-lived CLI
    # invocation. It is located / torn down by matching the forward spec.
    @property
    def _fwd(self) -> str:
        return "%d:127.0.0.1:%d" % (self.s.local_port, self.s.remote_port)

    def open_tunnel(self) -> CmdResult:
        if self.tunnel_alive():
            return CmdResult(0, "already running", "")
        argv = ["ssh", "-f", "-N", *self._base_opts(), "-L", self._fwd, self.s.ssh_target]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        time.sleep(1.0)
        return CmdResult(p.returncode, p.stdout, p.stderr)

    def tunnel_alive(self) -> bool:
        p = subprocess.run(["pgrep", "-f", "ssh.*-L %s" % self._fwd],
                           capture_output=True, text=True)
        return p.returncode == 0 and bool(p.stdout.strip())

    def close_tunnel(self) -> None:
        subprocess.run(["pkill", "-f", "ssh.*-L %s" % self._fwd], capture_output=True)
