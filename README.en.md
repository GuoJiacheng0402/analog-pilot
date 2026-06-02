# AnalogPilot

**An AI-agent-driven, scriptable Cadence analog/mixed-signal IC design flow,
tuned for the EDA servers of the School of Microelectronics, South China University of Technology (SCUT).**

> 中文文档是主文档，请见 [`README.md`](README.md)。This page is a short English
> summary for international readers.

## What it is

From your own laptop, drive the Cadence tools that live on your lab's Linux
server — Virtuoso (via SKILL), Spectre, and Calibre — through Python and a CLI.
It turns the "schematic → layout → DRC/LVS/PEX → post-layout simulation" loop,
normally done by hand in a VNC GUI, into something scriptable, reproducible, and
parallelizable.

It bundles three things:

1. **A self-contained bridge engine** (`src/apilot/`) for remote SKILL execution
   and Spectre simulation — independently implemented on Cadence's public SKILL
   IPC facility.
2. **A knowledge base** (`docs/`) — deployment guide, a troubleshooting handbook,
   a CSMC05_M3 PDK cheat-sheet, the post-layout verification flow, a simulation
   methodology guide, and collaboration conventions.
3. **Agent skills** (`skills/`) you can link into Claude Code / Cursor so your
   AI assistant understands this exact environment.

This project was distilled from a complete course-project run (an op-amp + a
bandgap reference, taken all the way through post-layout verification) so that
future students don't have to rediscover every pitfall.

## Quick start

```bash
git clone https://github.com/GuoJiacheng0402/analog-pilot.git
cd analog-pilot
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

apilot init <user@host>      # writes ~/.apilot/.env; then edit the placeholders
apilot start                 # SSH tunnel + deploy SKILL daemon
apilot status                # expect [tunnel] running / [daemon] OK
```

```python
from apilot import SkillClient
print(SkillClient.from_env().execute("1+2"))  # SkillResult(status=SUCCESS, output='3')
```

See [`docs/01_服务器部署指南.md`](docs/01_服务器部署指南.md) for the full guide.

## Originality

AnalogPilot is an independent, self-implemented project. Its bridge engine
(`src/apilot/`) is built from scratch on Cadence Virtuoso's public SKILL IPC
mechanism (`ipcBeginProcess` / `evalstring`) and does not copy, vendor, or
derive from third-party project code. Runtime package dependencies are declared
in [`pyproject.toml`](pyproject.toml). See [`NOTICE`](NOTICE).

## Academic use

If you use this project in coursework, a thesis, or any academic deliverable,
you must cite it (see [`CITATION.cff`](CITATION.cff)) and acknowledge it — both
under the GPL-3.0 §7(b) attribution-preservation term and as a matter of
academic integrity. See [`ACADEMIC_USE.md`](ACADEMIC_USE.md).

## License

[GPL-3.0-only](LICENSE), with a Section 7(b) attribution-preservation term.
Authored by **GuoJiacheng** (School of Microelectronics, SCUT), with AI-assisted
coding and documentation support from **Claude (Anthropic)**.
