ARG BENCH_SOURCE_IMAGE=cube-bench-suite:upstream-amd64
ARG CUBESANDBOX_BASE_IMAGE=ghcr.io/tencentcloud/cubesandbox-base:2026.16
FROM ${BENCH_SOURCE_IMAGE} AS bench-src

FROM ${CUBESANDBOX_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    CUBE_BENCH_HOME=/opt/cube-bench \
    CUBE_PROBE_PORT=49999 \
    ENVD_PORT=49983 \
    PIP_INDEX_URL=https://mirrors.tencent.com/pypi/simple \
    PIP_TRUSTED_HOST=mirrors.tencent.com \
    PATH=/opt/cube-bench/bin:/opt/cube-bench/bin/go-upstream:/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY --from=bench-src /usr/local/go /usr/local/go
COPY --from=bench-src /opt/cube-bench/bin /opt/cube-bench/bin
COPY --from=bench-src /opt/cube-bench/upstream /opt/cube-bench/upstream
COPY --from=bench-src /opt/cube-bench/vendor /opt/cube-bench/vendor
COPY --from=bench-src /opt/cube-bench/BENCHMARKS.md /opt/cube-bench/BENCHMARKS.md
COPY run-benchmark /opt/cube-bench/bin/run-benchmark
COPY health_server.py /opt/cube-bench/bin/health_server.py
COPY BENCHMARKS.md /opt/cube-bench/BENCHMARKS.md

WORKDIR /opt/cube-bench

RUN set -eux; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's#http://archive.ubuntu.com#http://mirrors.tencent.com#g; s#http://security.ubuntu.com#http://mirrors.tencent.com#g; s#http://ports.ubuntu.com#http://mirrors.tencent.com#g' /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl time jq procps iproute2 \
      build-essential make gcc g++ \
      autoconf automake libtool pkg-config libaio-dev libtirpc-dev \
      unzip zip \
      php-cli php-json php-mbstring php-opcache \
      python3 python3-pip python3-venv python3-setuptools python3-packaging \
      nodejs npm \
      default-jdk-headless; \
    pip3 install -i https://mirrors.tencent.com/pypi/simple --trusted-host mirrors.tencent.com pyperf packaging tomli; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    chmod +x /opt/cube-bench/bin/*; \
    rm -rf /opt/cube-bench/bin/go-upstream /opt/cube-bench/work; \
    mkdir -p /opt/cube-bench/bin/go-upstream /opt/cube-bench/work; \
    rm -rf /opt/cube-bench/upstream/sysbench-1.0.20; \
    cd /opt/cube-bench/upstream && tar -xf sysbench-1.0.20.tar.gz; \
    cd /opt/cube-bench/upstream/sysbench-1.0.20 && ./autogen.sh && ./configure --without-mysql && make -j"$(nproc)"; \
    install -m 0755 /opt/cube-bench/upstream/sysbench-1.0.20/src/sysbench /opt/cube-bench/bin/sysbench-upstream; \
    cd /opt/cube-bench/upstream/golang-benchmarks && GOTOOLCHAIN=local GOBIN=/opt/cube-bench/bin/go-upstream go install -mod=vendor ./build ./http ./json ./garbage; \
    printf '#!/usr/bin/env sh\ncd /opt/cube-bench/upstream/pyperformance\nexec python3 /opt/cube-bench/upstream/pyperformance/dev.py "$@"\n' > /opt/cube-bench/bin/pyperformance; \
    chmod +x /opt/cube-bench/bin/pyperformance; \
    /opt/cube-bench/bin/pyperformance --version; \
    PYPERFORMANCE_BENCHMARKS=python_startup /opt/cube-bench/bin/run-benchmark python-benchmark >/opt/cube-bench/work/pyperformance-build-smoke.log 2>&1 || true; \
    (cd /opt/cube-bench/upstream/php-bench && PHPBENCH_ERROR_REPORTING=1 php index.php action=list_suites format=json >/opt/cube-bench/work/phpbench-suites.json 2>&1) || true; \
    (cd /opt/cube-bench/upstream/benchmark-octane && node run.js >/opt/cube-bench/work/octane-build-smoke.log 2>&1) || true; \
    printf '# Benchmark Sources\n\n' > /opt/cube-bench/SOURCES.md; \
    for d in golang-benchmarks php-bench pyperformance benchmark-octane; do \
      printf -- '- %s: %s\n' "$d" "$(cat /opt/cube-bench/upstream/$d/.source-commit)" >> /opt/cube-bench/SOURCES.md; \
    done; \
    sha256sum /opt/cube-bench/upstream/scimark-2.2.jar /opt/cube-bench/upstream/sysbench-1.0.20.tar.gz >> /opt/cube-bench/SOURCES.md; \
    /opt/cube-bench/bin/run-benchmark versions || true

EXPOSE 49983 49999

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD curl -fsS "http://127.0.0.1:${ENVD_PORT:-49983}/health" >/dev/null || exit 1

CMD ["/opt/cube-bench/bin/health_server.py"]
