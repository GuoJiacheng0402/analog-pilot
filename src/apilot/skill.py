"""SkillClient: execute SKILL expressions in a remote Virtuoso via AnalogPilot.

Deploys the SKILL daemon + bridge to the remote host, opens an SSH tunnel, and
talks to the daemon over TCP using the length-prefixed framing in skill_daemon.py.
Independently written; uses only the standard library plus the local ssh/config
modules.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass
from importlib import resources
from pathlib import PurePosixPath

from .config import Settings, _get
from .ssh import SshSession

SUCCESS = "SUCCESS"
ERROR = "ERROR"


@dataclass
class SkillResult:
    status: str
    output: str

    def __repr__(self) -> str:
        return "SkillResult(status=%s, output=%r)" % (self.status, self.output)

    @property
    def ok(self) -> bool:
        return self.status == SUCCESS


def _resource_text(name: str) -> str:
    return resources.files(__package__).joinpath("resources", name).read_text(encoding="utf-8")


class SkillClient:
    """Client for executing SKILL in a remote Virtuoso process."""

    def __init__(self, settings: Settings, ssh: SshSession | None = None):
        self.s = settings
        self.ssh = ssh or SshSession(settings)

    @classmethod
    def from_env(cls, profile: str | None = None, env_path=None) -> "SkillClient":
        return cls(Settings.from_env(profile=profile, env_path=env_path))

    # -- remote deployment ------------------------------------------------
    @property
    def remote_dir(self) -> str:
        return str(PurePosixPath(self.s.scratch_root) / "apilot")

    @property
    def setup_il_path(self) -> str:
        return str(PurePosixPath(self.remote_dir) / "apilot_setup.il")

    def _remote_python(self) -> str:
        """Resolve an ABSOLUTE python path on the remote.

        ipcBeginProcess launches the daemon with the Virtuoso process's PATH,
        which often does not include the login-shell PATH — so a bare `python3`
        fails to launch. Resolve a full path (overridable via APILOT_REMOTE_PYTHON).
        """
        override = _get("REMOTE_PYTHON", self.s.profile)
        if override:
            return override
        r = self.ssh.run("command -v python3 || command -v python || which python3", timeout=20)
        for line in (r.out or "").splitlines():
            line = line.strip()
            if line.startswith("/"):
                return line
        return "python3"

    def deploy(self) -> str:
        """Upload the daemon + bridge to the remote host. Returns the setup.il path."""
        rdir = self.remote_dir
        daemon_path = str(PurePosixPath(rdir) / "skill_daemon.py")
        bridge_path = str(PurePosixPath(rdir) / "skill_bridge.il")
        python = self._remote_python()

        self.ssh.write_remote_text(_resource_text("skill_daemon.py"), daemon_path)
        self.ssh.write_remote_text(_resource_text("skill_bridge.il"), bridge_path)

        setup = (
            ';; AnalogPilot auto-generated setup. Load this in the CIW.\n'
            '(setq ApPython "%s")\n'
            '(setq ApDaemon "%s")\n'
            '(setq ApHost "127.0.0.1")\n'
            '(setq ApPort %d)\n'
            '(load "%s")\n'
        ) % (python, daemon_path, self.s.remote_port, bridge_path)
        self.ssh.write_remote_text(setup, self.setup_il_path)
        return self.setup_il_path

    def start(self) -> str:
        """Deploy the daemon and open the SSH tunnel. Returns the CIW load line."""
        self.deploy()
        self.ssh.open_tunnel()
        return 'load("%s")' % self.setup_il_path

    def stop(self) -> None:
        self.ssh.close_tunnel()

    # -- SKILL execution --------------------------------------------------
    def execute(self, skill: str, timeout: float = 30.0) -> SkillResult:
        """Send one SKILL expression to the remote daemon and return the result."""
        payload = skill.encode("utf-8")
        header = ("C%08d\n" % len(payload)).encode("ascii")
        with socket.create_connection(("127.0.0.1", self.s.local_port), timeout=timeout) as conn:
            conn.sendall(header + payload)
            # read reply: <status char><8-digit len>\n<payload>
            head = b""
            while b"\n" not in head:
                ch = conn.recv(1)
                if not ch:
                    return SkillResult(ERROR, "no response from daemon (tunnel down or daemon not loaded?)")
                head += ch
            line = head.rstrip(b"\n")
            status_char, length = chr(line[0]), int(line[1:])
            data = b""
            while len(data) < length:
                chunk = conn.recv(length - len(data))
                if not chunk:
                    break
                data += chunk
        out = data.decode("utf-8", "replace")
        return SkillResult(SUCCESS if status_char == "S" else ERROR, out)

    # backwards-friendly alias
    def execute_skill(self, skill: str, timeout: float = 30.0) -> SkillResult:
        return self.execute(skill, timeout=timeout)

    def load_il(self, remote_il_path: str, timeout: float = 60.0) -> SkillResult:
        return self.execute('load("%s")' % remote_il_path, timeout=timeout)

    def run_il_text(self, il_text: str, remote_tmp: str | None = None, timeout: float = 60.0) -> SkillResult:
        """Upload a (possibly large, multi-line) SKILL script and load() it."""
        remote_tmp = remote_tmp or str(PurePosixPath(self.remote_dir) / "_scratch.il")
        self.ssh.write_remote_text(il_text, remote_tmp)
        return self.load_il(remote_tmp, timeout=timeout)

    # -- file transfer passthrough ---------------------------------------
    def upload_text(self, text: str, remote_path: str):
        return self.ssh.write_remote_text(text, remote_path)

    def download_file(self, remote_path: str, local_path: str):
        return self.ssh.download(remote_path, local_path)

    # -- status -----------------------------------------------------------
    def status(self) -> dict:
        tunnel = self.ssh.tunnel_alive()
        daemon = "UNKNOWN"
        if tunnel:
            r = self.execute("1+2", timeout=10)
            daemon = "OK" if (r.ok and r.output.strip() == "3") else "NO RESPONSE"
        return {"tunnel": "running" if tunnel else "down", "daemon": daemon}
