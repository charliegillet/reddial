# Pin the base image (audit: `latest` is non-reproducible). Override at build
# with --build-arg PIPECAT_BASE=dailyco/pipecat-base:<tag>. Pin to a digest in
# prod (dailyco/pipecat-base@sha256:...) for full reproducibility.
ARG PIPECAT_BASE=dailyco/pipecat-base:0.0.8
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