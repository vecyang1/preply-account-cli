#!/usr/bin/env bash
# Weekly Preply Motivational Digest Pipeline (XinChaoVi)
# Scheduled to run every Monday at 09:00 AM via crontab

set -euo pipefail

PROJECT_DIR="/Users/vecsatfoxmailcom/Documents/A-coding/2026-05-29 preply-account-cli"
cd "$PROJECT_DIR"

mkdir -p data/digests

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting Preply Weekly Digest Pipeline ==="

/opt/homebrew/bin/python3 -m preply_cli digest run \
    --role both \
    --lang zh-CN \
    --push-crm \
    --draft \
    --site xinchaovi.com

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Completed Preply Weekly Digest Pipeline ==="
