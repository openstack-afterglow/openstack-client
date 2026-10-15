"""Keep tested image archives in GitLab Packages when the OCI registry is unavailable."""
import hashlib
import json
import os
from pathlib import Path

import requests


def main():
    flavor = os.environ["FLAVOR"]
    archive = Path(os.environ["CI_PROJECT_DIR"]) / f"openstack-client-{flavor}.tar.gz"
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    base = (
        f"{os.environ['CI_API_V4_URL']}/projects/{os.environ['CI_PROJECT_ID']}"
        f"/packages/generic/cloudshell-images/{os.environ['CI_COMMIT_SHA']}"
    )
    session = requests.Session()
    session.headers["JOB-TOKEN"] = os.environ["CI_JOB_TOKEN"]
    with archive.open("rb") as stream:
        uploaded = session.put(f"{base}/{archive.name}", data=stream, timeout=600)
        uploaded.raise_for_status()
    uploaded = session.put(
        f"{base}/{archive.name}.sha256",
        data=f"{checksum}  {archive.name}\n".encode(), timeout=30,
    )
    uploaded.raise_for_status()
    print(json.dumps({"archive": archive.name, "sha256": checksum, "download_url": f"{base}/{archive.name}"}))


if __name__ == "__main__":
    main()
