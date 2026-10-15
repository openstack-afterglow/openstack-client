# OpenStack Cloud Shell client

Maintained DMS fork of <https://gitlab.com/gbraad/openstack-client>, retaining its
Git history at upstream commit `d332a95c8e0180d82f248cd17b6fae81e6e27b67`.

The current image runs Python 3.12, OpenSSL 3 and the OpenStack CLI with Zun,
Barbican, Designate, Heat, Magnum, Manila, Octavia, Swift, Trove and Placement
plugins. The default user is `cloudshell` (UID/GID 1000), with a writable home
at `/home/cloudshell`. `/bin/bash`, login shells and Zun interactive terminals
are supported. Supply credentials at runtime through `clouds.yaml`, OpenRC or
environment variables. No credentials are built into the image.

## Published images

Registry: `glcr.dmslab.re.kr/system/openstack/openstack-client`

| Tag | Base | Purpose |
| --- | --- | --- |
| `latest`, `slim` | Python 3.12 / Debian Trixie | Default Cloud Shell image |
| `alpine` | Python 3.12 / Alpine 3.23 | Smaller alternative |
| `sha-<commit>-slim`, `sha-<commit>-alpine` | Same bases | Commit-specific builds |

CI builds Linux amd64 images using Kaniko on ordinary Docker runners without
privileged mode or a Docker daemon. Every build uploads its commit-specific
candidate tag and dependency cache to this project's registry. Separate jobs
run inside both images and check TLS 1.3 support, trusted certificates,
non-root operation, writable home and 13 CLI command groups. Only after both
tests pass are default-branch builds promoted to `slim`, `alpine` and `latest`.
Release tags publish `<release>-<flavor>`. Pin the published digest in production.

The inherited `alpine/`, `centos/`, `fedora/` and `ubuntu/` directories preserve
the original 2017 recipes. The maintained build uses the root `Dockerfile`.

## Use

```sh
docker run --rm -it \
  -v "$HOME/.config/openstack:/home/cloudshell/.config/openstack:ro" \
  glcr.dmslab.re.kr/system/openstack/openstack-client:slim
openstack --os-cloud mycloud server list
stack mycloud server list
```

For Zun, use the image digest, `command=["/bin/bash"]`, `interactive=true`,
`tty=true`, and a tenant network that reaches OpenStack public endpoints.
Configure registry credentials in Zun for the internal GitLab registry.
For Horizon, set `CLOUD_SHELL_IMAGE` to the validated image reference. This
repository supplies the standard CLI/shell runtime; application-specific
credential bootstrap helpers are supplied by their owning application.

## Build and validate

```sh
docker build -t openstack-client:local .
docker run --rm --network none openstack-client:local openstack-client-check
docker run --rm --network none openstack-client:local bash --login -c 'openstack --version'
```

Base image manifests are pinned by digest. `requirements.in` pins direct
dependencies; `requirements.lock` pins all Python dependencies with hashes.
Refresh the lock using uv:

```sh
uv pip compile --python-version 3.12 --generate-hashes \
  requirements.in --output-file requirements.lock
```

After updating, run both CI variants and validate a temporary Zun container
against the deployed OpenStack release, including public WSS attach and
authenticated read-only CLI calls. Keep TLS verification enabled.

## Registry outage recovery

When the registry is unavailable, run a pipeline with `BUILD_ARCHIVES_ONLY=true`.
Both Dockerfile variants run the runtime checks during their build, and CI
uploads gzip-compressed `docker load` archives and SHA-256 checksums to GitLab
Packages (`cloudshell-images/<full-commit>`). Download with an authenticated
GitLab Packages request, verify the checksum, and use `docker load` to import.
Registry-based test and tag-promotion jobs are skipped in this recovery mode.
Rerun a normal pipeline after the registry is repaired to publish the image tags.
