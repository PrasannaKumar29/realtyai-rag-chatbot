FROM python:3.11.18-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    CHROMA_PATH=/opt/realtyai/runtime_assets/chroma \
    CHUNKS_PATH=/opt/realtyai/runtime_assets/chunks.jsonl \
    TOKENIZER_CACHE=/opt/realtyai/runtime_assets/tokenizer \
    WASALT_LISTINGS_PATH=/opt/realtyai/runtime_assets/listings.jsonl \
    OPENROUTER_ENABLE_FALLBACK=false PORT=10000 HOME=/tmp
WORKDIR /opt/realtyai
COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt && pip check \
    && groupadd --gid 10001 realtyai && useradd --uid 10001 --gid 10001 --no-create-home realtyai
COPY app/ ./app/
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY runtime_assets/ ./runtime_assets/
COPY packaging/ ./packaging/
RUN chmod -R a+rX /opt/realtyai
USER 10001:10001
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','10000')+'/_stcore/health',timeout=4)"
ENTRYPOINT ["sh", "packaging/start.sh"]
