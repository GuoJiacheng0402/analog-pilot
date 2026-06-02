#!/usr/bin/env python3
"""最小连通性自检：连接桥接、执行一条 SKILL、报告 Virtuoso 工作环境。

前提：已执行 `apilot start`，且已在 CIW 中 load daemon
（见 docs/01_服务器部署指南.md）。

    python examples/01_connect_smoke_test.py
"""
from apilot import SkillClient


def main() -> None:
    client = SkillClient.from_env()

    # 1) 最基本的 SKILL：算术
    r = client.execute_skill("1+2")
    print("execute_skill('1+2') ->", r)
    assert r.output == "3", "桥接已连通但返回值异常，请检查 daemon 是否正常 load"

    # 2) 报告 Virtuoso 端的环境信息（不依赖任何 PDK）。
    #    此处仅作演示；环境探测以 `apilot status` 更为直接。
    info = client.execute_skill(
        'sprintf(nil "host=%s time=%L" getShellEnvVar("HOSTNAME") getCurrentTime())'
    )
    print("env probe ->", info)

    print("\n桥接连通正常。后续可参考 skills/csmc-pdk 与 docs/ 开始工作。")


if __name__ == "__main__":
    main()
