# Needle ships a manylinux (glibc) native library, so this add-on must use a
# Debian/glibc image. Supervisor supplies the target platform via --platform;
# this multi-architecture image supports both amd64 and aarch64.
# Keep all build defaults here: build.yaml is deprecated by Supervisor.
FROM python:3.11-slim-bookworm

ARG BUILD_ARCH=amd64
ARG NEEDLE_VERSION=3.1.0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Needle resolves its base weights below HOME. /data is mounted over by
# Supervisor at runtime, so keep the build-time model in the image.
ENV \
    HOME=/opt/needle-home \
    HF_HOME=/data/huggingface \
    JAX_PLATFORMS=cpu \
    NEEDLE3_LIB_PATH=/opt/needle-engine/libneedle.so \
    NEEDLE_TELEMETRY=0 \
    DO_NOT_TRACK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --no-cache-dir "cactus-needle==${NEEDLE_VERSION}" \
    # Needle 3.1.0 uses origin-root URLs (for example /style.css and /model).
    # Home Assistant ingress mounts the app below a tokenized path, so make all
    # bundled UI resources and API calls relative to that ingress path.
    && playground="/usr/local/lib/python3.11/site-packages/needle/playground" \
    && grep -Fq 'href="/style.css"' "${playground}/index.html" \
    && grep -Fq 'src="/app.js"' "${playground}/index.html" \
    && grep -Fq 'fetch("/' "${playground}/app.js" \
    && grep -Fq 'dl.href = "/download/' "${playground}/app.js" \
    && sed -i \
        -e 's|href="/style.css"|href="./style.css"|g' \
        -e 's|src="/app.js"|src="./app.js"|g' \
        "${playground}/index.html" \
    && sed -i \
        -e 's|fetch("/|fetch("./|g' \
        -e 's|dl.href = "/download/|dl.href = "./download/|g' \
        "${playground}/app.js" \
    && case "${BUILD_ARCH}" in \
        amd64) platform_tag="manylinux2014_x86_64" ;; \
        aarch64) platform_tag="manylinux2014_aarch64" ;; \
        *) echo "Unsupported architecture: ${BUILD_ARCH}" >&2; exit 1 ;; \
    esac \
    && mkdir -p /opt/needle-engine \
    && needle fetch \
        --generation 3 \
        --out /opt/needle-engine \
        --platform-tag "${platform_tag}" \
    # Needle 3 separates the engine from the base .cact weights. Download the
    # weights into the default cache below HOME so playground can load them
    # without network access and still report calibrated confidence.
    && python3 -c 'from needle.agent.fetch import fetch_weights; from pathlib import Path; paths = [Path(fetch_weights(g)) for g in (3, "whistle")]; assert all(p.is_file() and p.stat().st_size > 0 for p in paths)' \
    && test -s /opt/needle-engine/libneedle.so

# Both base models are baked into HOME; disable Hub requests at runtime.
ENV HF_HUB_OFFLINE=1

COPY rootfs /

RUN chmod 0755 /app/entrypoint.sh /app/healthcheck.sh

WORKDIR /data

EXPOSE 7860

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=2m \
    --retries=3 \
    CMD ["/app/healthcheck.sh"]

ARG BUILD_DATE
ARG BUILD_DESCRIPTION="Run the Cactus Compute Needle 3 local tool-calling playground and Whistle speech recognition"
ARG BUILD_NAME="Needle 3"
ARG BUILD_REF
ARG BUILD_REPOSITORY=dzervas/ha-addon-needle-conversation
ARG BUILD_VERSION

LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    maintainer="Dimitris Zervas" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Dimitris Zervas" \
    org.opencontainers.image.authors="Dimitris Zervas" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/addon-needle-3/DOCS.md" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"
