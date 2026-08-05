# ---- builder stage: compile python deps with uv -----------------
FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim@sha256:096c3761e41782bdb2818381a8202153d39e0618a9e12c757a2c46327c1aa83c AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Build-time headers only; runtime libs installed in the final stage.
# libimage-exiftool-perl is needed at build time because pyexifinfo's
# setup.py probes for the exiftool binary during wheel install.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    zlib1g-dev \
    libopenjp2-7-dev \
    libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock /app/

# Semantic bulletin search is opt-in: it pulls torch and transformers, which
# add roughly 2 GB to the image. Build with --build-arg WITH_SEMANTIC=true
# (docker-compose-dev.yml sets it) to enable it.
ARG WITH_SEMANTIC=false
RUN uv sync --frozen --no-install-project

# Installed separately from the lockfile, and deliberately from PyTorch's CPU
# index: the default torch wheel drags in several GB of NVIDIA CUDA libraries
# that a CPU-only server never loads. Versions are pinned so the build stays
# reproducible even though these are not in uv.lock.
RUN if [ "$WITH_SEMANTIC" = "true" ]; then \
        uv pip install --python /app/.venv/bin/python \
            --index-url https://download.pytorch.org/whl/cpu \
            "torch==2.8.0" \
        && uv pip install --python /app/.venv/bin/python \
            "sentence-transformers==5.6.1"; \
    fi

# Bake the embedding model into the image so the running container never needs
# network access. This is the only step that requires internet, and it happens
# at build time, not at runtime.
ARG SEMANTIC_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV SEMANTIC_MODEL_PATH=/app/models/semantic
# Always create the directory so the runtime COPY succeeds even when the
# model was not built.
RUN mkdir -p /app/models
RUN if [ "$WITH_SEMANTIC" = "true" ]; then \
        .venv/bin/python -c "\
from sentence_transformers import SentenceTransformer; \
m = SentenceTransformer('${SEMANTIC_MODEL}'); \
m.save('${SEMANTIC_MODEL_PATH}'); \
print('model saved to ${SEMANTIC_MODEL_PATH}')"; \
    fi

# ---- runtime stage -----------------------------------------------
FROM python:3.12-slim-bookworm@sha256:76d4b7b6305788c6b4c6a19d6a22a3921bf802e9af4d5e1e5bd771208dba74bf AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    XDG_CACHE_HOME=/tmp/.cache

ARG ROLE
ENV ROLE=${ROLE}

# Shared runtime libs: psycopg2 (libpq5), weasyprint (pango/cairo/harfbuzz),
# pillow (libjpeg, libopenjp2), lxml (libxml2, libxslt).
# Celery roles also need exiftool + ffmpeg for media processing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libxml2 \
    libxslt1.1 \
    libjpeg62-turbo \
    libopenjp2-7 \
    zlib1g \
    libffi8 \
    fonts-dejavu-core \
    && if [ "$ROLE" = "celery" ] || [ "$ROLE" = "celery-ocr" ]; then \
         apt-get install -y --no-install-recommends \
           libimage-exiftool-perl \
           ffmpeg; \
       fi \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --system --create-home --uid 1000 ubuntu

COPY --chown=ubuntu:ubuntu . /app
COPY --from=builder --chown=ubuntu:ubuntu /app/.venv /app/.venv

# Embedding model (absent unless built with WITH_SEMANTIC=true). The offline
# flags guarantee transformers never reaches for the network at runtime, even
# if a model file were missing -- it fails loudly instead of calling out.
COPY --from=builder --chown=ubuntu:ubuntu /app/models /app/models
ENV SEMANTIC_MODEL_PATH=/app/models/semantic \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY --chown=ubuntu:ubuntu ./flask/bin/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 550 /usr/local/bin/entrypoint.sh

# .dockerignore excludes these paths, so they are absent from the image. Docker
# creates a missing volume mountpoint as root, which the ubuntu process cannot
# write to; pre-creating them seeds the named volumes with the right ownership.
RUN mkdir -p /app/logs /app/backups /app/enferno/media /app/enferno/imports \
    && chown ubuntu:ubuntu /app/logs /app/backups /app/enferno/media /app/enferno/imports

USER ubuntu

CMD ["/usr/local/bin/entrypoint.sh"]
