#!/bin/bash
# analog-pilot :: BGR wrapper
# Source : https://github.com/GuoJiacheng0402/analog-pilot
set -e
cd "$(dirname "$0")"
python3 bgr_verify.py "$@"
