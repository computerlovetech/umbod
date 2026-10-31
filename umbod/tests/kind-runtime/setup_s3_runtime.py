import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


BUCKET = "umbod-runtime-content"
ENDPOINT = "http://umbod-runtime-s3:5000"


def kubectl(*arguments: str, payload: str = "") -> str:
    result = subprocess.run(
        ["kubectl", "--context", os.environ["UMBOD_TEST_KUBE_CONTEXT"], *arguments],
        input=payload, text=True, capture_output=True, check=True,
    )
    return result.stdout


def apply(document: dict[str, Any]) -> None:
    kubectl("apply", "-f", "-", payload=json.dumps(document))


def credentials() -> list[dict[str, Any]]:
    return [{"name": name, "valueFrom": {"secretKeyRef": {
        "name": "umbod-runtime-s3", "key": name,
    }}} for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")]


def provision() -> None:
    apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "umbod-runtime-s3"}, "stringData": {
        name: os.environ["UMBOD_TEST_" + name] for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    }})
    apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "umbod-runtime-s3"}, "data": {
        "setup_s3_runtime.py": Path(__file__).read_text(),
    }})
    apply({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "umbod-runtime-s3"}, "spec": {
        "replicas": 1, "selector": {"matchLabels": {"app": "umbod-runtime-s3"}}, "template": {
            "metadata": {"labels": {"app": "umbod-runtime-s3"}}, "spec": {"containers": [{
                "name": "s3-emulator", "image": os.environ["UMBOD_TEST_S3_IMAGE"], "imagePullPolicy": "Never",
                "ports": [{"containerPort": 5000}],
                "readinessProbe": {"httpGet": {"path": "/", "port": 5000}, "periodSeconds": 2},
            }]},
        },
    }})
    apply({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "umbod-runtime-s3"}, "spec": {
        "selector": {"app": "umbod-runtime-s3"}, "ports": [{"port": 5000, "targetPort": 5000}],
    }})
    kubectl("rollout", "status", "deployment/umbod-runtime-s3", "--timeout=3m")
    deployment = json.loads(kubectl("get", "deployment", "umbod-core", "-o", "json"))
    pod = deployment["spec"]["template"]["spec"]
    volume = {"name": "s3-fixture", "configMap": {"name": "umbod-runtime-s3"}}
    mount = {"name": "s3-fixture", "mountPath": "/s3-fixture", "readOnly": True}
    apply({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "umbod-runtime-s3-bucket"}, "spec": {
        "backoffLimit": 0, "activeDeadlineSeconds": 120, "template": {"spec": {
            "restartPolicy": "Never", "volumes": [volume], "containers": [{
                "name": "bucket", "image": pod["containers"][0]["image"], "imagePullPolicy": "Never",
                "command": ["python", "/s3-fixture/setup_s3_runtime.py", "bucket"],
                "env": credentials(), "volumeMounts": [mount],
            }],
        }},
    }})
    kubectl("wait", "--for=condition=complete", "job/umbod-runtime-s3-bucket", "--timeout=2m")
    settings = {
        "UMBOD_FILESYSTEM_CONTENT_BACKEND": "s3", "UMBOD_FILESYSTEM_S3_BUCKET": BUCKET,
        "UMBOD_FILESYSTEM_S3_REGION": "us-east-1", "UMBOD_FILESYSTEM_S3_ENDPOINT_URL": ENDPOINT,
        "UMBOD_FILESYSTEM_S3_PREFIX": "runtime", "UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE": "path",
    }
    for container in pod["containers"]:
        container["env"] = [entry for entry in container.get("env", []) if entry["name"] not in (*settings, "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")]
        container["env"].extend({"name": name, "value": value} for name, value in settings.items())
        container["env"].extend(credentials())
        container.setdefault("volumeMounts", []).append(mount)
    pod.setdefault("volumes", []).append(volume)
    kubectl("patch", "deployment", "umbod-core", "--type=json", "-p", json.dumps([
        {"op": "replace", "path": "/spec/template/spec", "value": pod},
    ]))
    kubectl("rollout", "status", "deployment/umbod-core", "--timeout=3m")


async def inspect_storage(operation: str) -> None:
    from aiobotocore.session import get_session
    from botocore.config import Config

    async with get_session().create_client(
        "s3", region_name="us-east-1", endpoint_url=ENDPOINT,
        config=Config(s3={"addressing_style": "path"}),
    ) as client:
        if operation == "bucket":
            await client.create_bucket(Bucket=BUCKET)
            await client.head_bucket(Bucket=BUCKET)
            return
        objects = []
        async for page in client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):
            objects.extend({"key": item["Key"], "size": item["Size"], "etag": item["ETag"]} for item in page.get("Contents", []))
        sys.stdout.write(json.dumps(objects))


def main() -> None:
    if len(sys.argv) == 1:
        provision()
    else:
        asyncio.run(inspect_storage(sys.argv[1]))


if __name__ == "__main__":
    main()
