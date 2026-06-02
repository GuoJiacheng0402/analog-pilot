#!/bin/bash
# analog-pilot :: OPA wrapper
# Source : https://github.com/GuoJiacheng0402/analog-pilot
set -e
cd "$(dirname "$0")"
python3 opa_verify.py "$@"
