FROM python:3.12-slim

ARG SHAKA_VERSION=v3.5.0

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && curl -fsSL -o /usr/local/bin/packager \
       "https://github.com/shaka-project/shaka-packager/releases/download/${SHAKA_VERSION}/packager-linux-x64" \
    && chmod +x /usr/local/bin/packager \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir .

ENTRYPOINT ["hlspkg"]
