# OpenStack Cloud Shell client

Maintained DMS fork of <https://gitlab.com/gbraad/openstack-client>, retaining its
Git history at upstream commit `d332a95c8e0180d82f248cd17b6fae81e6e27b67` and the
updated GitLab source at `434529e`. The maintained source and GHCR build owner is
<https://github.com/openstack-afterglow/openstack-client>. The GitLab origin and
its independent publication pipeline remain available; GitLab is not the GHCR
publication path.

The image retains Python 3.12, OpenSSL 3, the hashed CLI dependency lock and Zun,
Barbican, Designate, Heat, Magnum, Manila, Octavia, Swift, Trove and Placement
plugins. The default user is `cloudshell` (UID/GID 1000), with persistent home
`/home/cloudshell` and isolated CLI environment `/opt/openstack`. The default
command remains `/bin/bash --login`, not a daemon. Generic CLI users can supply
`clouds.yaml`, OpenRC or environment variables at runtime. No credentials belong
in the build context or image.

## Published images

Canonical registry: `ghcr.io/openstack-afterglow/openstack-client`

| Tag | Base | Platforms |
| --- | --- | --- |
| `latest`, `slim` | Python 3.12 / Debian Trixie (default) | `linux/amd64`, `linux/arm64` |
| `alpine` | Python 3.12 / Alpine 3.23 | `linux/amd64`, `linux/arm64` |
| `sha-<full-commit>-run-<run-id>-attempt-<attempt>-<flavor>` | Run-unique tested revision manifest | Both platforms |
| `sha-<full-commit>-run-<run-id>-attempt-<attempt>-<flavor>-<arch>` | Run-unique tested architecture candidate | Named architecture |
| `v<release>`, `v<release>-slim`, `v<release>-alpine` | Release tag aliases; unqualified release is Debian | Both platforms |

The GitHub Actions workflow builds all four combinations on native GitHub Linux
runners (`ubuntu-24.04`, `ubuntu-24.04-arm`). Every combination must pass source
PTY regressions, the actual non-root CLI check and the real setuid PTY image
smoke before publication starts. The smoke uses `--network none --pull never`,
synthetic credentials and a unique disposable home volume. It never contacts a
cloud or inference endpoint. Builds themselves need network access for pinned
base images and locked dependencies.

PR jobs have read-only repository permissions, never log in to GHCR, never push,
and never hand PR artifacts to a privileged workflow. There is no
`pull_request_target`. Only main pushes, `v[0-9]*` tag pushes, and manual runs on
main or such tags can publish. A separate package-write job loads the exact four
successfully tested image archives; it does not rebuild or check out source.
It pushes run-unique full-revision architecture candidates, resolves their exact
registry digests, creates a checked multiarchitecture manifest from those digests,
then promotes its digest to channels on main or version aliases on tags. A rebuild
at the same source SHA uses a different run/attempt reference rather than
overwriting a previous commit candidate.
Release tags do not change `latest`. Action revisions are pinned by full commit.

Run-unique revision tags are never reused by this workflow. Registry owners can
still retag them manually; use the published **manifest digest**, not a tag, for
an immutable production reference. Do not retarget source release tags.
A failed registry upload or promotion fails the workflow; it is not a successful publication. The workflow
summary records revision manifests. No publication is claimed until that exact
source SHA's Actions run and registry digests have been inspected.

The retained GitLab CI publishes independently to
`glcr.dmslab.re.kr/system/openstack/openstack-client` using its existing Kaniko
amd64 path and CLI gates. It does not provide the GitHub all-four/runtime gate.
The inherited `alpine/`, `centos/`, `fedora/` and `ubuntu/` directories preserve
2017 recipes; only the root `Dockerfile` is maintained.

## Private registry operations

The GitHub source repository is private; keep the initial GHCR package private
and verify its actual ACL after first publication. Org package creation policy
must permit this repository's `GITHUB_TOKEN` to publish, and the
package must grant the repository Actions access. The workflow uses only its
job-scoped token (`packages: write` in the publication job); no personal access
token is needed in Actions and no credentials are passed as build arguments.
Native arm64 runners and sufficient Actions/artifact quota must be available to
the private repository. Missing runner access is a failed/queued gate, not a
reason to skip arm64.

For an operator pull, use a separately authorized registry identity with only
`read:packages` and required org authorization, via Docker's credential store or
`docker login ghcr.io --password-stdin`. Never put registry secrets in Git,
Cloud Shell settings, browser code, shell history, image layers or CLI payloads.
Repository visibility and package visibility are separate; verify the actual
package ACL rather than assuming that a private source repository permits a
compute host to pull.

For private Zun pulls, create/manage the registry credential using Zun's own
registry service with an approved read-only identity. Configure Afterglow's
optional Cloud Shell registry ID to select that Zun-owned entry. The Zun API
create field is `registry` (registry responses use `registry_id`). Configure the
canonical image or validated digest independently; `image_pull_policy` is
optional (`always`, `ifnotpresent`, `never`) and explicit policy selection may
require an administrator under stock Zun policy. An unset policy leaves the
field out. A missing/inaccessible image must fail normally; there is no fallback
image. This repository does not configure live tenant registries or credentials.

## Use

After authorized registry login when required:

```sh
docker run --rm -it \
  -v "$HOME/.config/openstack:/home/cloudshell/.config/openstack:ro" \
  ghcr.io/openstack-afterglow/openstack-client:slim
openstack --os-cloud mycloud server list
stack mycloud server list
```

For generic Zun use, select a validated image digest, a shell command,
`interactive=true`, `tty=true`, and a tenant network reaching the intended
OpenStack endpoints. Do not use root or `--privileged` to make the helper work.

## Afterglow bootstrap contract

Afterglow invokes `/usr/local/bin/afterglow-cloud-shell-bootstrap` with no
arguments through a PTY as UID/GID 1000. This binary is root-owned mode **4755**,
compiled in the matching Debian/Alpine builder. It accepts only real UID 1000,
effective root and effective GID 1000, clears the environment and supplementary
groups, and executes isolated `/opt/openstack/bin/python -I` with the root-owned
mode0644 `/usr/local/libexec/afterglow-cloud-shell-bootstrap.py`. No Python
package installer or additional dependency system is introduced for the helper.
Both bases expose `/bin/setpriv`; login shells retain `/opt/openstack/bin`
at the start of PATH.

Protocol, unchanged from Afterglow:

1. Disable PTY echo, then emit `AFTERGLOW_CLOUD_SHELL_READY_V1` plus newline.
2. Accept one base64url-encoded JSON line, with at most 16 KiB of encoded payload.
   Its exact top-level keys are `clouds` and `secure`. The single cloud is
   `afterglow`, using `v3token` authentication with scoped project/token data.
3. Atomically write `clouds.yaml` and `secure.yaml` as JSON (valid YAML) under
   `/dev/shm/afterglow`, mode0600 UID/GID1000. The directory is root-owned,
   group1000 mode0750; the underlying `/dev/shm` must be tmpfs. Never persist the
   token to `/home/cloudshell`, command arguments or the container environment.
4. Emit `AFTERGLOW_CLOUD_SHELL_OK_V1`, restore terminal settings, and replace the
   process with a UID/GID1000 `/bin/bash --login` using `setpriv`: cleared groups,
   no-new-privileges and empty inheritable, ambient and bounding capabilities.
   On rejected input/runtime failure, emit `AFTERGLOW_CLOUD_SHELL_ERROR_V1` without
   printing credential details. No credential echo is permitted.

The generated public file has the SDK-required top-level `clouds` mapping.
The shell explicitly sets both `OS_CLIENT_CONFIG_FILE` and
`OS_CLIENT_SECURE_FILE` to their generated files; `XDG_CONFIG_HOME` alone is not
sufficient because SDK discovery appends an `openstack` subdirectory. The wire
payload shape and handshake markers remain unchanged.

The home is preserved and set mode0700; symlinked home/config paths are rejected.
Only the home is a persistent mount. `/dev/shm` credentials disappear on
container replacement, and a fresh session bootstraps again. Once the shell has
dropped capabilities and set no-new-privileges, it cannot regain root through
the launcher. The authorized attach/bootstrap process is separate from commands
running inside that unprivileged shell.

The initial launcher requires setuid to be effective. A rootless/user-namespaced
runtime, `nosuid`, container-level no-new-privileges, dropped bootstrap-required
capabilities, or a hardened security profile can prevent it working. Do not
weaken the profile or add a root fallback; qualify the actual Zun runtime.
Setuid correctness and glibc/musl ABI compatibility must be exercised on both
architectures, not inferred from compilation or emulation alone.

## Build and verify all four images

Run source tests without additional packages (Python 3.12+):

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run this from the repository root on Docker engines capable of executing each
requested architecture. Native engines are preferred; cross-architecture
emulation is an additional environmental risk and is not native CI evidence.
These commands build locally and do not push. All runtime checks are offline:

```sh
set -eu
for flavor in slim alpine; do
  case "$flavor" in
    slim) base='python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1' ;;
    alpine) base='python:3.12-alpine3.23@sha256:1fd55c2f838c4f76262f9eeed899ff9168ea96ac383c61667d6f204325e1f169' ;;
  esac
  for arch in amd64 arm64; do
    image="openstack-client:$flavor-$arch"
    docker buildx build --load --platform "linux/$arch" \
      --build-arg "PYTHON_IMAGE=$base" --build-arg "VCS_REF=$(git rev-parse HEAD)" \
      --tag "$image" .
    python3 tests/image_smoke.py "$image" --platform "linux/$arch"
  done
done
```

The smoke explicitly starts `bash -c 'exec sleep infinity'`; a detached default
login shell would exit immediately. It checks default non-root CLI execution,
real setuid launch and PTY echo suppression, shell UID/GID/capability drop,
private tmpfs token ownership/mode, installed SDK loading of the scoped cloud and
token with an initialized auth session (without making a cloud request),
persistent-home replacement and absence of a token in the replacement container
before the next bootstrap. Its cleanup is limited to uniquely named smoke
containers and their dedicated volume.

Base image manifests remain digest-pinned. `requirements.in` pins direct CLI
dependencies and `requirements.lock` pins all Python dependencies with hashes.
For an intentional dependency refresh only:

```sh
uv pip compile --python-version 3.12 --generate-hashes \
  requirements.in --output-file requirements.lock
```

Then run all four image gates. Before live acceptance, qualify a disposable Zun
container against the deployed OpenStack version, public WSS attach, intended
registry permissions and authenticated read-only CLI calls, with TLS validation
on. Offline source/image tests do not establish live registry or cloud acceptance.

## Source audit and license status

The current tracked source has no embedded production registry/cloud credentials
identified in the targeted pre-upload review. CI credential references are
runtime variables. Historical 2017 README commits contain literal username and
password examples; whether those ever represented live credentials is unknown.
Retained history must not be described as secret-free or made public without an
owner decision and appropriate historical-secret review. History was not rewritten.

No repository-level LICENSE or explicit license grant was found for the supplied
original openstack-client tree/history; this migration does not relicense it.
The copied Afterglow bootstrap C/Python code and migrated tests retain their MIT
notice in `LICENSE.afterglow` (copyright 2026 봉정근). The runtime image includes
that notice at `/usr/local/share/licenses/afterglow-cloud-shell/LICENSE`.
Dependency licenses remain their respective owners' licenses. Keep the repository
private pending an explicit licensing/publication decision for the original code.
