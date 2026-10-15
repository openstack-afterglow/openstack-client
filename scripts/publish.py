"""Promote tested commit images using the authenticated OCI Registry API."""
import hashlib
import json
import os
import re
from urllib.parse import urlsplit

import requests


def main():
    registry = os.environ["CI_REGISTRY"]
    image = os.environ["CI_REGISTRY_IMAGE"]
    repository = image.removeprefix(registry + "/")
    if repository == image:
        raise RuntimeError("Unexpected registry image prefix")
    session = requests.Session()
    challenge = session.get(f"https://{registry}/v2/", timeout=30)
    fields = dict(re.findall(r'(\w+)="([^"]+)"', challenge.headers.get("WWW-Authenticate", "")))
    realm = fields["realm"]
    if urlsplit(realm).hostname != os.environ["CI_SERVER_HOST"]:
        raise RuntimeError("Unexpected registry authentication server")
    auth = session.get(realm, params={
        "service": fields["service"], "scope": f"repository:{repository}:pull,push",
    }, auth=(os.environ["CI_REGISTRY_USER"], os.environ["CI_REGISTRY_PASSWORD"]), timeout=30)
    auth.raise_for_status()
    session.headers["Authorization"] = "Bearer " + auth.json()["token"]
    session.headers["Accept"] = ", ".join([
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ])
    results = []
    for flavor in ["slim", "alpine"]:
        source = f"sha-{os.environ['CI_COMMIT_SHORT_SHA']}-{flavor}"
        response = session.get(f"https://{registry}/v2/{repository}/manifests/{source}", timeout=30)
        response.raise_for_status()
        manifest = response.content
        digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        aliases = []
        if os.environ.get("CI_COMMIT_BRANCH") == os.environ["CI_DEFAULT_BRANCH"]:
            aliases += [flavor]
            if flavor == "slim":
                aliases += ["latest"]
        if os.environ.get("CI_COMMIT_TAG"):
            aliases += [f"{os.environ['CI_COMMIT_TAG']}-{flavor}"]
        for alias in aliases:
            url = f"https://{registry}/v2/{repository}/manifests/{alias}"
            promoted = session.put(url, data=manifest, headers={
                "Content-Type": response.headers["Content-Type"],
            }, timeout=30)
            promoted.raise_for_status()
            if promoted.headers.get("Docker-Content-Digest") != digest:
                raise RuntimeError("Published digest differs from the tested image")
        results.append({"flavor": flavor, "source": source, "digest": digest, "tags": aliases})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
