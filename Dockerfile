FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch==2.9.0'
COPY pyproject.toml constraints.txt ./
RUN python -c "import tomllib; p=tomllib.load(open('pyproject.toml','rb'))['project']; print('\n'.join(p['dependencies']+p['optional-dependencies']['vision']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -c constraints.txt -r /tmp/requirements.txt 'setuptools==80.9.0'

FROM dependencies AS app
COPY src ./src
COPY scripts/prepare_charades.py scripts/run_charades.py scripts/evaluate_retrieval.py ./scripts/
RUN pip install --no-cache-dir --no-deps --no-build-isolation . \
    && useradd --create-home --uid 10001 app && mkdir -p /models /uploads /uploaded-media \
    && chown app:app /models /uploads /uploaded-media
USER app
CMD ["uvicorn", "video_search.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS vision

FROM vision AS test
USER root
RUN pip install --no-cache-dir -c constraints.txt '.[test]'
COPY tests ./tests
COPY evaluation/qvhighlights-public-example.json ./evaluation/qvhighlights-public-example.json
COPY scripts/evaluate_retrieval.py ./scripts/evaluate_retrieval.py
COPY scripts/sol/prepare_temporal.py ./scripts/sol/prepare_temporal.py
COPY scripts/compare_temporal_decoders.py ./scripts/compare_temporal_decoders.py
COPY scripts/evaluate_temporal_head.py ./scripts/evaluate_temporal_head.py
COPY scripts/summarize_temporal_heads.py ./scripts/summarize_temporal_heads.py
COPY scripts/sol/prepare_sdst.py ./scripts/sol/prepare_sdst.py
COPY scripts/sol/prepare_sdst_runtime.py ./scripts/sol/prepare_sdst_runtime.py
USER app
CMD ["pytest", "-q"]
