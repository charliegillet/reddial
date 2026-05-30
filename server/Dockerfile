# Pin the base image (audit: `latest` is non-reproducible). Override at build
# with --build-arg PIPECAT_BASE=dailyco/pipecat-base:<tag>. Pin to a digest in
# prod (dailyco/pipecat-base@sha256:...) for full reproducibility.
#
# IMPORTANT: dailyco/pipecat-base is published for linux/arm64 ONLY (Pipecat
# Cloud runs arm64). It has NO linux/amd64 manifest, so this image MUST be built
# for arm64 (e.g. `docker buildx build --platform linux/arm64`). On an amd64
# host/CI runner that means QEMU emulation — see .github/workflows/ci.yml.
#
# The previous default `0.0.8` did not exist on Docker Hub (lowest real tag is
# 0.1.2); `FROM` failed with a manifest-not-found error on every build. Pinned
# below to a real, current tag whose multi-arch index digest is recorded for
# reproducibility (py3.12 satisfies the project's requires-python >=3.11).
#   dailyco/pipecat-base:0.1.20-py3.12
#   @sha256:6a64272104c307776101fd9b77bf6b6ded77026c5f7f0d23af21b7f564f65281
ARG PIPECAT_BASE=dailyco/pipecat-base:0.1.20-py3.12
FROM ${PIPECAT_BASE}

# Default deploy role: the deliberately-vulnerable target. Override per deploy
# (target | attacker | flower). See bot.py dispatcher.
ENV REDDIAL_ROLE=target
# Outbound dialing is OFF unless explicitly enabled at deploy time (safety gate).
ENV REDDIAL_DIALING_ENABLED=

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Uncomment if you wish to print a summary of the features available in the base image
# ENV PCC_LOG_FEATURES_SUMMARY=true

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy the application code.
# bot.py is the Pipecat entrypoint the base image runs. RedDial adds the voice
# layer (attacker_bot.py / target_bot.py) plus the loopback/scoring modules. We
# copy every top-level module so the image has the full RedDial harness; a glob
# is used so the build does not fail if a not-yet-written module is absent.
COPY ./*.py ./