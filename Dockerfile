# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
FROM ${PYTHON_IMAGE} AS builder
RUN if command -v apk >/dev/null; then \
      apk add --no-cache build-base libffi-dev openssl-dev; \
    else \
      apt-get update && apt-get install -y --no-install-recommends build-essential libffi-dev libssl-dev \
      && rm -rf /var/lib/apt/lists/*; \
    fi
RUN python -m venv /opt/openstack
COPY requirements.lock /tmp/requirements.lock
RUN /opt/openstack/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
    && /opt/openstack/bin/pip check
FROM ${PYTHON_IMAGE} AS runtime
ARG VCS_REF=local
ARG SOURCE_URL=https://git.dmslab.re.kr/system/openstack/openstack-client
LABEL org.opencontainers.image.title="DMS OpenStack Cloud Shell" \
      org.opencontainers.image.description="Python 3.12 OpenStack CLI with TLS 1.3 and Zun support" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${VCS_REF}"
RUN if command -v apk >/dev/null; then \
      apk add --no-cache bash bash-completion ca-certificates curl bind-tools git iproute2 iputils jq less openssh-client openssl procps tini util-linux \
      && addgroup -g 1000 cloudshell \
      && adduser -D -u 1000 -G cloudshell -h /home/cloudshell -s /bin/bash cloudshell; \
    else \
      apt-get update && apt-get install -y --no-install-recommends bash bash-completion ca-certificates curl dnsutils git iproute2 iputils-ping jq less openssh-client openssl procps tini util-linux \
      && rm -rf /var/lib/apt/lists/* \
      && groupadd --gid 1000 cloudshell \
      && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/cloudshell --shell /bin/bash cloudshell; \
    fi \
    && mkdir -p /workspace /home/cloudshell/.stack /home/cloudshell/.config/openstack \
    && chown -R 1000:1000 /workspace /home/cloudshell
COPY --from=builder /opt/openstack /opt/openstack
COPY --chmod=0644 scripts/profile.sh /etc/profile.d/openstack-client.sh
COPY --chmod=0755 scripts/stack /usr/local/bin/stack
COPY --chmod=0755 scripts/check.py /usr/local/bin/openstack-client-check
ENV PATH="/opt/openstack/bin:${PATH}" \
    HOME="/home/cloudshell" \
    SHELL="/bin/bash" \
    TERM="xterm-256color" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    PIP_DISABLE_PIP_VERSION_CHECK="1"
USER 1000:1000
WORKDIR /home/cloudshell
RUN openstack-client-check \
    && /bin/bash --login -c 'openstack --version && test "$(id -u)" = 1000'
CMD ["/bin/bash", "--login"]
