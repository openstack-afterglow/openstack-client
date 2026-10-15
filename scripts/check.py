#!/opt/openstack/bin/python
"""Offline runtime checks; credentials and cloud access are not required."""
import importlib.metadata
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile


def main():
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or later is required")
    if not ssl.HAS_TLSv1_3:
        raise RuntimeError("The runtime must support TLS 1.3")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    if not context.cert_store_stats()["x509_ca"]:
        raise RuntimeError("No trusted CA certificates found")
    home = Path.home()
    if os.getuid() != 1000 or str(home) != "/home/cloudshell":
        raise RuntimeError("Unexpected Cloud Shell user or home directory")
    with tempfile.TemporaryFile(dir=home):
        pass
    commands = [
        ["--version"], ["server", "list", "--help"], ["network", "list", "--help"],
        ["appcontainer", "list", "--help"], ["secret", "list", "--help"],
        ["recordset", "list", "--help"], ["stack", "list", "--help"],
        ["coe", "cluster", "list", "--help"], ["share", "list", "--help"],
        ["loadbalancer", "list", "--help"], ["database", "instance", "list", "--help"],
        ["object", "store", "account", "show", "--help"],
        ["resource", "provider", "list", "--help"],
    ]
    for args in commands:
        proc = subprocess.run(["openstack", *args], capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise RuntimeError(f"Command check failed: openstack {' '.join(args)}\n{proc.stderr}")
    print(json.dumps({
        "result": "passed", "python": sys.version.split()[0],
        "openssl": ssl.OPENSSL_VERSION, "tls_1_3": ssl.HAS_TLSv1_3,
        "openstackclient": importlib.metadata.version("python-openstackclient"),
        "openstacksdk": importlib.metadata.version("openstacksdk"),
        "zunclient": importlib.metadata.version("python-zunclient"),
        "uid": os.getuid(), "home": str(home), "command_checks": len(commands),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
