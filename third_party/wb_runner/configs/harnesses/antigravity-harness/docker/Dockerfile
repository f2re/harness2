# Antigravity CLI split-mount image for WorkBuddy-Bench.
# Google publishes agy as a native Linux executable through its official installer.
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl bash && \
    rm -rf /var/lib/apt/lists/*
ENV HOME=/root
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash && \
    test -x /root/.local/bin/agy && /root/.local/bin/agy --version
RUN mkdir -p /out/bin && cp /root/.local/bin/agy /out/bin/agy && chmod 0755 /out/bin/agy

FROM scratch
COPY --from=build /out/bin/ /bin/
