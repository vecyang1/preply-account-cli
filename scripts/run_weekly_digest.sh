#!/usr/bin/env bash
# Weekly Preply Motivational Digest Pipeline (XinChaoVi)
# Scheduled to run every Monday at 09:00 AM via crontab

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p data/digests

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting Preply Weekly Digest Pipeline ==="

${PYTHON_BIN:-python3} -m preply_cli digest run \
    --role both \
    --lang zh-CN \
    --push-crm \
    --draft \
    --site xinchaovi.com

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Completed Preply Weekly Digest Pipeline ==="
