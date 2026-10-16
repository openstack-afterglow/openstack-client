"""Root-only Cloud Shell credential bootstrap with an explicit PTY handshake."""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
import stat
import termios
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

BOOTSTRAP_READY_MARKER = b"AFTERGLOW_CLOUD_SHELL_READY_V1\n"
BOOTSTRAP_OK_MARKER = b"AFTERGLOW_CLOUD_SHELL_OK_V1\n"
BOOTSTRAP_ERROR_MARKER = b"AFTERGLOW_CLOUD_SHELL_ERROR_V1\n"
BOOTSTRAP_MAX_BYTES = 16 * 1024
CLOUD_SHELL_UID = 1000
CLOUD_SHELL_GID = 1000
HOME_PATH = Path("/home/cloudshell")
CONFIG_PATH = Path("/dev/shm/afterglow")

ExecShell = Callable[[str, list[str], dict[str, str]], Any]


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("terminal closed during Cloud Shell bootstrap")
        view = view[written:]


def _read_payload_line(fd: int) -> bytes:
    chunks = bytearray()
    while len(chunks) <= BOOTSTRAP_MAX_BYTES:
        chunk = os.read(fd, min(4096, BOOTSTRAP_MAX_BYTES + 1 - len(chunks)))
        if not chunk:
            raise ValueError("bootstrap input closed")
        chunks.extend(chunk)
        newline = chunks.find(b"\n")
        if newline >= 0:
            if newline != len(chunks) - 1:
                raise ValueError("bootstrap input contains trailing data")
            return bytes(chunks[:newline]).rstrip(b"\r")
    raise ValueError("bootstrap input exceeded the size limit")


def _decode_payload(encoded: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if not encoded or len(encoded) > BOOTSTRAP_MAX_BYTES:
        raise ValueError("bootstrap input has an invalid size")
    try:
        raw = base64.b64decode(encoded, altchars=b"-_", validate=True)
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("bootstrap input is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {"clouds", "secure"}:
        raise ValueError("bootstrap input has invalid top-level keys")

    clouds = payload["clouds"]
    secure = payload["secure"]
    if not isinstance(clouds, dict) or set(clouds) != {"afterglow"}:
        raise ValueError("bootstrap cloud configuration is malformed")
    cloud = clouds["afterglow"]
    if not isinstance(cloud, dict) or set(cloud) != {
        "auth_type",
        "auth",
        "region_name",
        "interface",
        "identity_api_version",
    }:
        raise ValueError("bootstrap cloud configuration is malformed")
    auth = cloud["auth"]
    if (
        cloud["auth_type"] != "v3token"
        or not isinstance(auth, dict)
        or set(auth) != {"auth_url", "project_id"}
        or not all(isinstance(auth[key], str) and auth[key] for key in ("auth_url", "project_id"))
        or not isinstance(cloud["region_name"], str)
        or not cloud["region_name"]
        or not isinstance(cloud["interface"], str)
        or not cloud["interface"]
        or cloud["identity_api_version"] != 3
    ):
        raise ValueError("bootstrap cloud configuration is malformed")

    if not isinstance(secure, dict) or set(secure) != {"clouds"}:
        raise ValueError("bootstrap secure configuration is malformed")
    secure_clouds = secure["clouds"]
    if not isinstance(secure_clouds, dict) or set(secure_clouds) != {"afterglow"}:
        raise ValueError("bootstrap secure configuration is malformed")
    secure_cloud = secure_clouds["afterglow"]
    if not isinstance(secure_cloud, dict) or set(secure_cloud) != {"auth"}:
        raise ValueError("bootstrap secure configuration is malformed")
    secure_auth = secure_cloud["auth"]
    if not isinstance(secure_auth, dict) or set(secure_auth) != {"token"}:
        raise ValueError("bootstrap secure configuration is malformed")
    token = secure_auth["token"]
    if not isinstance(token, str) or not token or len(token) > 8192 or "\n" in token or "\r" in token:
        raise ValueError("bootstrap token is malformed")
    return clouds, secure


def _atomic_private_json(directory_fd: int, name: str, value: dict[str, Any], *, uid: int, gid: int) -> None:
    temporary_name = f".{name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
    try:
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
        _write_all(fd, payload)
        os.fchmod(fd, 0o600)
        os.fchown(fd, uid, gid)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.rename(temporary_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=directory_fd)


def _open_private_runtime_directory(path: Path, *, gid: int) -> int:
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        with suppress(FileExistsError):
            os.mkdir(path.name, 0o750, dir_fd=parent_fd)
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise ValueError("Cloud Shell configuration path is not a directory")
            os.fchown(fd, os.geteuid(), gid)
            os.fchmod(fd, 0o750)
            os.fsync(fd)
        except Exception:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(parent_fd)


def _prepare_runtime(
    encoded: bytes,
    *,
    home_path: Path,
    config_path: Path,
    uid: int,
    gid: int,
) -> None:
    clouds, secure = _decode_payload(encoded)

    home_fd = os.open(home_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if not stat.S_ISDIR(os.fstat(home_fd).st_mode):
            raise ValueError("Cloud Shell home is not a directory")
        os.fchown(home_fd, uid, gid)
        os.fchmod(home_fd, 0o700)
        os.fsync(home_fd)
    finally:
        os.close(home_fd)

    config_fd = _open_private_runtime_directory(config_path, gid=gid)
    try:
        _atomic_private_json(config_fd, "clouds.yaml", {"clouds": clouds}, uid=uid, gid=gid)
        _atomic_private_json(config_fd, "secure.yaml", secure, uid=uid, gid=gid)
    finally:
        os.close(config_fd)


def _shell_environment() -> dict[str, str]:
    term = os.environ.get("TERM", "xterm-256color")
    if not term or len(term) > 64 or any(not (char.isalnum() or char in "-_.") for char in term):
        term = "xterm-256color"
    return {
        "HOME": str(HOME_PATH),
        "LOGNAME": "cloudshell",
        "OS_CLIENT_CONFIG_FILE": str(CONFIG_PATH / "clouds.yaml"),
        "OS_CLIENT_SECURE_FILE": str(CONFIG_PATH / "secure.yaml"),
        "OS_CLOUD": "afterglow",
        "PATH": "/opt/openstack/bin:/usr/local/bin:/usr/bin:/bin",
        "SHELL": "/bin/bash",
        "TERM": term,
        "USER": "cloudshell",
        "XDG_CONFIG_HOME": str(CONFIG_PATH),
    }


def _exec_shell(path: str, argv: list[str], environment: dict[str, str]) -> None:
    os.execve(path, argv, environment)


def run_bootstrap(
    stdin_fd: int,
    stdout_fd: int,
    *,
    home_path: Path = HOME_PATH,
    config_path: Path = CONFIG_PATH,
    uid: int = CLOUD_SHELL_UID,
    gid: int = CLOUD_SHELL_GID,
    exec_shell: ExecShell = _exec_shell,
) -> int:
    """Complete the one-line credential handshake, then replace the process with an unprivileged shell."""
    terminal_state = termios.tcgetattr(stdin_fd)
    quiet_state = terminal_state.copy()
    quiet_state[3] &= ~(termios.ECHO | termios.ECHONL)
    termios.tcsetattr(stdin_fd, termios.TCSANOW, quiet_state)
    restored = False
    try:
        _write_all(stdout_fd, BOOTSTRAP_READY_MARKER)
        encoded = _read_payload_line(stdin_fd)
        _prepare_runtime(encoded, home_path=home_path, config_path=config_path, uid=uid, gid=gid)
        _write_all(stdout_fd, BOOTSTRAP_OK_MARKER)
        termios.tcsetattr(stdin_fd, termios.TCSANOW, terminal_state)
        restored = True
        argv = [
            "setpriv",
            f"--reuid={uid}",
            f"--regid={gid}",
            "--clear-groups",
            "--no-new-privs",
            "--inh-caps=-all",
            "--ambient-caps=-all",
            "--bounding-set=-all",
            "/bin/bash",
            "--login",
        ]
        exec_shell("/bin/setpriv", argv, _shell_environment())
        return 0
    except Exception:
        _write_all(stdout_fd, BOOTSTRAP_ERROR_MARKER)
        return 1
    finally:
        if not restored:
            termios.tcsetattr(stdin_fd, termios.TCSANOW, terminal_state)


def main() -> int:
    return run_bootstrap(0, 1)


if __name__ == "__main__":
    raise SystemExit(main())
