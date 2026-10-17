# OpenStack Cloud Shell client

Enhanced and maintained DMS version of Gerard Braad's original
<https://gitlab.com/gbraad/openstack-client>, retaining its Git history at upstream
commit `d332a95c8e0180d82f248cd17b6fae81e6e27b67` and the updated DMS GitLab source
at `434529e`. The maintained source and GHCR build owner is
<https://github.com/openstack-afterglow/openstack-client>. The GitLab origin and
its independent publication pipeline remain available; GitLab is not the GHCR
publication path.

The maintained changes include Python 3.12, OpenSSL 3, a hashed CLI dependency
lock with Zun, Barbican, Designate, Heat, Magnum, Manila, Octavia, Swift, Trove
and Placement plugins, a non-root tmpfs credential bootstrap, and native
amd64/arm64 CI with gated GHCR publication. The default user is `cloudshell` (UID/GID 1000), with persistent home
`/home/cloudshell` and isolated CLI environment `/opt/openstack`. The default
command remains `/bin/bash --login`, not a daemon. Generic CLI users can supply
`clouds.yaml`, OpenRC or environment variables at runtime. No credentials belong
in the build context or image.

## Published images

Canonical registry: `ghcr.io/openstack-afterglow/openstack-client`

| Tag | Base | Platforms |
| --- | --- | --- |
| `2025.2`, `2025.2-slim`, `latest`, `slim` | Python 3.12 / Debian Trixie (default) | `linux/amd64`, `linux/arm64` |
| `2025.2-alpine`, `alpine` | Python 3.12 / Alpine 3.23 | `linux/amd64`, `linux/arm64` |
| `sha-<full-commit>-run-<run-id>-attempt-<attempt>-<flavor>` | Run-unique tested revision manifest | Both platforms |
| `sha-<full-commit>-run-<run-id>-attempt-<attempt>-<flavor>-<arch>` | Run-unique tested architecture candidate | Named architecture |
| `v<release>`, `v<release>-slim`, `v<release>-alpine` | Release tag aliases; unqualified release is Debian | Both platforms |

The `2025.2` family is a **moving compatibility channel**, not an immutable
release. Only publication from `main` updates these channels (and the generic
`latest`/`slim`/`alpine` channels). A `v<release>` publication updates only its
version aliases; it must not move any moving channel, including `2025.2`.
The declared OpenStack series/compatibility label describes the target cloud
series. It is neither the Kolla Ansible binary version nor proof of live
compatibility. A deployment can report a different Kolla Ansible package version;
only a live check against that deployment establishes interoperability.

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
then promotes its digest to channels on main or version aliases on tags. The
publication gate also checks registry digests, logs out and performs anonymous
pulls and CLI checks; an authenticated push alone does not establish public
pullability. A rebuild at the same source SHA uses a different run/attempt
reference rather than overwriting a previous commit candidate.
Release tags do not change moving channels. Action revisions are pinned by full commit.

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

## Public registry operations

The GitHub source repository and canonical GHCR package are intentionally public
by the owner's explicit publication decision. Public GHCR pulls are anonymous:
operators do not need a GitHub account, a personal access token or `docker login`.
Repository visibility and package visibility are separate settings; the owner
selects **Public** in the GHCR package settings, and publication must pass the
anonymous pull gate. A public source repository alone does not prove a package's
ACL or that a particular new tag has been published.

Actions still requires job-scoped `GITHUB_TOKEN` authorization to push
(`packages: write` in the publication job), package creation permission and
repository Actions access to the package. No personal access token is needed
in Actions and no credentials are passed as build arguments. Native arm64
runners and sufficient Actions/artifact quota must be available. Missing runner
access is a failed/queued gate, not a reason to skip arm64.

For Zun, select the canonical public image or a validated digest and leave the
optional Afterglow Cloud Shell registry ID unset: no Zun registry credential is
needed for an anonymous GHCR pull. `image_pull_policy` is optional (`always`,
`ifnotpresent`, `never`) and explicit selection may require an administrator under
stock Zun policy. An unset policy leaves the field out. A missing/inaccessible
image must fail normally; there is no fallback image. Never put registry or
cloud secrets in Git, browser code, image layers or CLI payload logs.

## Use

Pull anonymously and start a shell (no registry login):

```sh
docker pull ghcr.io/openstack-afterglow/openstack-client:2025.2
docker run --rm -it \
  -v "$HOME/.config/openstack:/home/cloudshell/.config/openstack:ro" \
  ghcr.io/openstack-afterglow/openstack-client:2025.2
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

The non-root build gate also requires the project Apache license, NOTICE and
retained MIT notice to be readable as UID 1000. License directories are mode0755
and notice files mode0644; a successful root-only file read is not sufficient.

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

The targeted pre-upload review identified no embedded production registry/cloud
credentials in the current tracked source; this is not a claim that all retained
history is secret-free. CI credential references are runtime variables.
Historical README username/password examples were introduced in **2016**, including
[`0e889137` (2016-07-17)](https://gitlab.com/gbraad/openstack-client/-/commit/0e88913720fda76fab4befe63985771b6041d6f5).
Whether those examples ever represented live credentials, or are valid now, is
unknown; no live validity assertion is made. The owner explicitly chose public
publication with the retained history and this disclosed risk. History was not
rewritten. That decision does not establish original-author licensing permission.

### License scope and upstream evidence

The owner selects **Apache-2.0 for this maintained project's own original
contributions**, excluding inherited material and the existing MIT-covered
bootstrap/tests. The canonical Apache License 2.0 text is in [`LICENSE`](LICENSE);
[`NOTICE`](NOTICE) records the exact scope and provenance. This choice follows
[Kolla Ansible stable/2025.2's Apache-2.0 license](https://opendev.org/openstack/kolla-ansible/src/branch/stable/2025.2/LICENSE),
not a grant of permission from Kolla or from the original openstack-client author.

The reachable [upstream project metadata](https://gitlab.com/api/v4/projects/1348805?license=true)
reports `license: null` and `license_url: null`. Its
[master tree](https://gitlab.com/api/v4/projects/1348805/repository/tree?recursive=true&per_page=100)
has no `LICENSE`, `COPYING` or `NOTICE`, and its
[README](https://gitlab.com/gbraad/openstack-client/-/blob/master/README.md)
contains attribution but no explicit license grant. The supplied local
license-file history likewise yielded no original upstream grant. These bounded
checks do not prove that permission exists nowhere; **the original upstream
material's license remains unresolved**. Public hosting is not a license grant.
The owner cannot relicense other authors' work by selecting Apache-2.0; obtain
the rights holders' grant before treating the inherited material as cleared for
redistribution. Neither retained history nor third-party dependencies is relicensed.

The copied Afterglow bootstrap C/Python code in `bootstrap/` and migrated tests in
`tests/` retain their MIT grant in [`LICENSE.afterglow`](LICENSE.afterglow)
(Copyright (c) 2026 봉정근). All existing copyright notices are retained.
Upstream credits Gerard Braad as author, Lars Kellogg-Stedman's
[OpenStack Tools](https://github.com/larsks/openstack-tools), and GitLab's
infrastructure; this maintained version preserves that attribution in `NOTICE`.

Runtime license notices are installed at
`/usr/local/share/licenses/openstack-client/LICENSE` and
`/usr/local/share/licenses/openstack-client/NOTICE`; the existing MIT notice stays
at `/usr/local/share/licenses/afterglow-cloud-shell/LICENSE`. The OCI
`org.opencontainers.image.licenses="Apache-2.0 AND MIT"` label summarizes this
project's known grants only: it is not clearance for unresolved inherited work
or a complete license inventory for the base image and dependencies. Those
components retain their respective owners' licenses.

