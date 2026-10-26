#!/usr/bin/env bash
# Prepare a machine (e.g. a fresh Claude cloud session) to analyse data and render reports.
# usage: bash report_kit/setup_env.sh [font_dir]
#   - installs the Python packages the analysis scripts need (PyPI is reachable from cloud sessions)
#   - downloads Noto Sans SC / Noto Serif SC from npm for offline PDF export (only the weights the pages use)
#   - prints the environment variables for make_pdf.mjs and shot.mjs
set -euo pipefail
FONT_DIR="${1:-${TMPDIR:-/tmp}/report-fonts}"

python3 -c "import pandas, numpy, scipy, statsmodels, arch, PIL" 2>/dev/null \
  || pip install -q pandas numpy scipy statsmodels arch pillow

if [ ! -f "$FONT_DIR/sans/package/400.css" ]; then
  mkdir -p "$FONT_DIR/sans" "$FONT_DIR/serif" "$FONT_DIR/tgz"
  (cd "$FONT_DIR/tgz" && npm pack -s @fontsource/noto-sans-sc@5 @fontsource/noto-serif-sc@5 >/dev/null)
  tar -xzf "$FONT_DIR"/tgz/fontsource-noto-sans-sc-*.tgz -C "$FONT_DIR/sans" --wildcards \
      'package/400.css' 'package/500.css' 'package/700.css' 'package/files/*-400-normal.woff2' 'package/files/*-500-normal.woff2' 'package/files/*-700-normal.woff2'
  tar -xzf "$FONT_DIR"/tgz/fontsource-noto-serif-sc-*.tgz -C "$FONT_DIR/serif" --wildcards \
      'package/600.css' 'package/700.css' 'package/files/*-600-normal.woff2' 'package/files/*-700-normal.woff2'
  rm -rf "$FONT_DIR/tgz"
fi

PW=playwright
[ -f /opt/node-tools/node_modules/playwright/index.js ] && PW=/opt/node-tools/node_modules/playwright/index.js
command -v pdftoppm >/dev/null || echo "note: pdftoppm (poppler-utils) missing; pdf_pages.py needs it"
echo "export PLAYWRIGHT=$PW FONT_DIR=$FONT_DIR"
