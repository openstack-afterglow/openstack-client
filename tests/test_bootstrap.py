from __future__ import annotations

import base64
import importlib.util
import json
import os
import pty
import select
import stat
import threading
import time
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bootstrap", Path(__file__).resolve().parents[1] / "bootstrap/bootstrap.py"
)
assert _spec is not None and _spec.loader is not None
bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootstrap)


def _payload(token: str, *, extra: bool = False) -> bytes:
    value = {
        "clouds": {
            "afterglow": {
                "auth_type": "v3token",
                "auth": {"auth_url": "https://identity.example.test/v3", "project_id": "project-a"},
                "region_name": "RegionOne",
                "interface": "internal",
                "identity_api_version": 3,
            }
        },
        "secure": {"clouds": {"afterglow": {"auth": {"token": token}}}},
    }
    if extra:
        value["unexpected"] = True
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()) + b"\n"


def _read_until(fd: int, marker: bytes, *, timeout: float = 3) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while marker not in output and time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.1)
        if not readable:
            continue
        try:
            output.extend(os.read(fd, 4096))
        except OSError:
            break
    assert marker in output, bytes(output)
    return bytes(output)


def _run(
    home: Path,
    config: Path,
    encoded: bytes,
    *,
    expect_error: bool = False,
) -> tuple[int, bytes, tuple[str, list[str], dict[str, str]] | None]:
    master_fd, slave_fd = pty.openpty()
    result: list[int] = []
    invoked: list[tuple[str, list[str], dict[str, str]]] = []

    def fake_exec(path: str, argv: list[str], environment: dict[str, str]) -> None:
        invoked.append((path, argv, environment))

    thread = threading.Thread(
        target=lambda: result.append(
            bootstrap.run_bootstrap(
                slave_fd,
                slave_fd,
                home_path=home,
                config_path=config,
                uid=os.getuid(),
                gid=os.getgid(),
                exec_shell=fake_exec,
            )
        )
    )
    thread.start()
    output = bytearray(_read_until(master_fd, b"AFTERGLOW_CLOUD_SHELL_READY_V1\r\n"))
    os.write(master_fd, encoded)
    terminal_marker = b"AFTERGLOW_CLOUD_SHELL_ERROR_V1\r\n" if expect_error else b"AFTERGLOW_CLOUD_SHELL_OK_V1\r\n"
    output.extend(_read_until(master_fd, terminal_marker))
    thread.join(timeout=3)
    assert not thread.is_alive()
    os.close(master_fd)
    os.close(slave_fd)
    return result[0], bytes(output), invoked[0] if invoked else None


def test_bootstrap_hides_token_writes_private_config_and_drops_privileges(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = tmp_path / "run"
    home.mkdir(mode=0o755)
    config.mkdir(mode=0o700)
    encoded = _payload("secret-token-value")

    result, output, invoked = _run(home, config, encoded)

    assert result == 0
    assert encoded.strip() not in output
    assert b"secret-token-value" not in output
    assert json.loads((config / "secure.yaml").read_text())["clouds"]["afterglow"]["auth"]["token"] == (
        "secret-token-value"
    )
    assert json.loads((config / "clouds.yaml").read_text())["clouds"]["afterglow"]["auth"]["project_id"] == "project-a"
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    assert stat.S_IMODE((config / "clouds.yaml").stat().st_mode) == 0o600
    assert stat.S_IMODE((config / "secure.yaml").stat().st_mode) == 0o600
    assert invoked is not None
    _path, argv, environment = invoked
    assert "--no-new-privs" in argv
    assert "--bounding-set=-all" in argv
    assert argv[-2:] == ["/bin/bash", "--login"]
    assert environment["OS_CLOUD"] == "afterglow"
    assert environment["HOME"] == "/home/cloudshell"
    assert environment["OS_CLIENT_CONFIG_FILE"] == "/dev/shm/afterglow/clouds.yaml"
    assert environment["OS_CLIENT_SECURE_FILE"] == "/dev/shm/afterglow/secure.yaml"
    assert environment["XDG_CONFIG_HOME"] == "/dev/shm/afterglow"
    assert environment["PATH"].split(":")[0] == "/opt/openstack/bin"


def test_bootstrap_preserves_persistent_home_across_sessions(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = tmp_path / "run"
    home.mkdir()
    config.mkdir()
    sentinel = home / "persisted.txt"
    sentinel.write_text("survives")

    first, _, _ = _run(home, config, _payload("token-one"))
    second, _, _ = _run(home, config, _payload("token-two"))

    assert first == second == 0
    assert sentinel.read_text() == "survives"
    assert "token-two" in (config / "secure.yaml").read_text()
    assert "token-one" not in (config / "secure.yaml").read_text()


def test_bootstrap_rejects_unknown_payload_without_echoing_secret(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = tmp_path / "run"
    home.mkdir()
    config.mkdir()
    encoded = _payload("must-not-echo", extra=True)

    result, output, invoked = _run(home, config, encoded, expect_error=True)

    assert result == 1
    assert invoked is None
    assert encoded.strip() not in output
    assert b"must-not-echo" not in output
    assert not (config / "secure.yaml").exists()


def test_bootstrap_rejects_symlinked_home(tmp_path: Path) -> None:
    actual_home = tmp_path / "actual-home"
    actual_home.mkdir()
    home = tmp_path / "home"
    home.symlink_to(actual_home, target_is_directory=True)
    config = tmp_path / "run"
    config.mkdir()

    result, _, invoked = _run(home, config, _payload("token"), expect_error=True)

    assert result == 1
    assert invoked is None
    assert not (config / "secure.yaml").exists()


def test_bootstrap_rejects_symlinked_runtime_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    actual_config = tmp_path / "actual-run"
    actual_config.mkdir()
    config = tmp_path / "run"
    config.symlink_to(actual_config, target_is_directory=True)

    result, _, invoked = _run(home, config, _payload("token"), expect_error=True)

    assert result == 1
    assert invoked is None
    assert not (actual_config / "secure.yaml").exists()


class BootstrapTests(unittest.TestCase):
    """Run the migrated PTY regression cases without installing test dependencies."""

    def test_payload_limit_and_malformed_inputs(self) -> None:
        for encoded in (b"", b"not-base64!", b"a" * (16 * 1024 + 1)):
            with self.subTest(encoded_length=len(encoded)):
                with self.assertRaises(ValueError):
                    bootstrap._decode_payload(encoded)

    def test_line_limit_and_trailing_data(self) -> None:
        for data in (b"a" * (16 * 1024 + 1), b"first\nsecond\n"):
            with tempfile.TemporaryFile() as stream:
                stream.write(data)
                stream.seek(0)
                with self.assertRaises(ValueError):
                    bootstrap._read_payload_line(stream.fileno())


def _temporary_case(case):
    def run_case():
        with tempfile.TemporaryDirectory() as directory:
            case(Path(directory))
    return run_case


def load_tests(loader, tests, pattern):
    for name, case in sorted(globals().items()):
        if name.startswith("test_bootstrap_") and callable(case):
            tests.addTest(unittest.FunctionTestCase(_temporary_case(case), description=name))
    return tests


if __name__ == "__main__":
    unittest.main()
