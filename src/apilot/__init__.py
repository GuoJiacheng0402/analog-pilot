"""AnalogPilot — an independent bridge for driving a remote Cadence Virtuoso
(via SKILL over SSH) and running standalone Spectre simulations.

Public API:

    from apilot import SkillClient, SpectreRunner, Settings

    client = SkillClient.from_env()        # reads ~/.apilot/.env
    client.start()                          # tunnel + deploy daemon (paste CIW line)
    print(client.execute("1+2"))            # SkillResult(status=SUCCESS, output='3')
"""
from .config import Settings
from .skill import SkillClient, SkillResult, SUCCESS, ERROR
from .spectre import SpectreRunner, parse_psf_ascii
from .layout import LayoutEditor

__version__ = "1.1.0"
__all__ = [
    "Settings",
    "SkillClient",
    "SkillResult",
    "SpectreRunner",
    "parse_psf_ascii",
    "LayoutEditor",
    "SUCCESS",
    "ERROR",
]
