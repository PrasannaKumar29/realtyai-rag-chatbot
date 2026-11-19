#!/bin/sh
set -eu
exec python -B -m streamlit run app/streamlit_app.py \
  --server.address=0.0.0.0 --server.port="${PORT:-10000}" \
  --server.headless=true --browser.gatherUsageStats=false
