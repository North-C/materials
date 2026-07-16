ARG ENVD_REF=2026.16
ARG GO_VERSION=1.25.4
ARG UBUNTU_VERSION=22.04
ARG TARGETARCH=arm64

FROM golang:${GO_VERSION}-bookworm AS envd-builder

ARG ENVD_REF
ARG ENVD_UPSTREAM_REPO=https://github.com/e2b-dev/infra.git
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --depth 1 --branch "${ENVD_REF}" "${ENVD_UPSTREAM_REPO}" infra

WORKDIR /src/infra/packages/envd

RUN commit_sha="$(git -C /src/infra rev-parse --short HEAD)" \
    && echo "Building envd from ${ENVD_UPSTREAM_REPO}@${ENVD_REF} (commit=${commit_sha})" \
    && CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH} \
       go build -a \
           -ldflags "-X=main.commitSHA=${commit_sha} -s -w" \
           -o /out/envd \
           . \
    && chmod +x /out/envd \
    && /out/envd -version \
    && /out/envd -commit

FROM ubuntu:${UBUNTU_VERSION}

ARG ENVD_REF
ARG DEBIAN_FRONTEND=noninteractive

ENV ENVD_REF=${ENVD_REF} \
    ENVD_PORT=49983 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN if [ -f /etc/apt/sources.list ]; then \
      sed -i 's#http://archive.ubuntu.com#http://mirrors.tencent.com#g; s#http://security.ubuntu.com#http://mirrors.tencent.com#g; s#http://ports.ubuntu.com#http://mirrors.tencent.com#g' /etc/apt/sources.list; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        sudo \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash user \
    && echo 'user ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/user \
    && chmod 0440 /etc/sudoers.d/user

COPY --from=envd-builder /out/envd /usr/bin/envd
COPY cube-entrypoint.sh /usr/local/bin/cube-entrypoint.sh

RUN chmod +x /usr/bin/envd /usr/local/bin/cube-entrypoint.sh \
    && mkdir -p /var/log \
    && printf '%s\n' "${ENVD_REF}" > /etc/cubesandbox-envd-ref \
    && /usr/bin/envd -version \
    && /usr/bin/envd -commit

LABEL org.opencontainers.image.source="https://github.com/TencentCloud/CubeSandbox" \
      org.opencontainers.image.title="cubesandbox-base" \
      org.opencontainers.image.description="CubeSandbox base image with envd compiled from e2b-dev/infra@${ENVD_REF}" \
      org.opencontainers.image.licenses="Apache-2.0" \
      io.cubesandbox.envd.ref="${ENVD_REF}"

EXPOSE 49983

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/cube-entrypoint.sh"]
CMD []
