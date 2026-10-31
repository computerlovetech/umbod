import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def run_kubectl(arguments: tuple[str, ...], payload: str) -> str:
    completed = subprocess.run(["kubectl", "--context", os.environ["UMBOD_TEST_KUBE_CONTEXT"], *arguments], input=payload, text=True, capture_output=True, check=True)
    return completed.stdout


def kubectl(*arguments: str) -> str:
    return run_kubectl(arguments, "")


def apply(document: dict[str, Any]) -> None:
    run_kubectl(("apply", "-f", "-"), json.dumps(document))


def upstream_identity(directory: Path) -> dict[str, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = directory / "identity.key"
    private_path.touch(mode=0o600)
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public_key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public_key.update({"kid": "kind-personal-jwt", "use": "sig", "alg": "RS256"})
    issued = int(time.time())
    for suffix, subject in (("a", "kind-ci"), ("b", "kind-ci-b")):
        token = jwt.encode({"sub": subject, "email": subject + "@example.invalid", "groups": ["admin"], "iss": "https://identity.personal-runtime.kind.invalid/", "aud": "kind-client", "iat": issued, "exp": issued + 3600}, key, algorithm="RS256", headers={"kid": "kind-personal-jwt"})
        token_path = directory / f"bearer-{suffix}"
        token_path.touch(mode=0o600)
        token_path.write_text(token + "\n")
    return {"keys": [public_key]}


def main() -> None:
    directory = Path(sys.argv[1])
    source = Path(__file__).parent
    jwks = upstream_identity(directory)
    apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "personal-runtime-identity"}, "stringData": {"identity.key": (directory / "identity.key").read_text(), "client-secret": "kind-disposable-identity-client-secret", "bearer-a": (directory / "bearer-a").read_text().strip(), "bearer-b": (directory / "bearer-b").read_text().strip()}})
    (directory / "ca.conf").write_text("[req]\ndistinguished_name=identity\nx509_extensions=authority\nprompt=no\n[identity]\nCN=Kind disposable personal CA\n[authority]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-config", str(directory / "ca.conf"), "-keyout", str(directory / "ca.key"), "-out", str(directory / "ca.crt"), "-days", "2"], check=True, capture_output=True)
    subprocess.run(["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(directory / "tls.key"), "-out", str(directory / "server.csr"), "-subj", "/CN=personal-runtime.kind.invalid"], check=True, capture_output=True)
    (directory / "extensions").write_text("subjectAltName=DNS:personal-runtime.kind.invalid,DNS:identity.personal-runtime.kind.invalid,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always,issuer\nkeyUsage=critical,digitalSignature,keyEncipherment\n")
    subprocess.run(["openssl", "x509", "-req", "-in", str(directory / "server.csr"), "-CA", str(directory / "ca.crt"), "-CAkey", str(directory / "ca.key"), "-CAcreateserial", "-out", str(directory / "tls.crt"), "-days", "2", "-extfile", str(directory / "extensions")], check=True, capture_output=True)
    apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "personal-runtime-tls"}, "type": "kubernetes.io/tls", "stringData": {name: (directory / name).read_text() for name in ("tls.crt", "tls.key")}})
    apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "personal-runtime"}, "data": {"ca.crt": (directory / "ca.crt").read_text(), "personal_fixture.py": (source / "personal_fixture.py").read_text(), "jwks.json": json.dumps(jwks)}})
    deployment = json.loads(kubectl("get", "deployment", "umbod-core", "-o", "json"))
    pod = deployment["spec"]["template"]["spec"]
    primary = next(container for container in pod["containers"] if container["name"] == "mcp")
    apply({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "personal-runtime"}, "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "personal-runtime"}}, "template": {"metadata": {"labels": {"app": "personal-runtime"}}, "spec": {"containers": [{"name": "fixture", "image": primary["image"], "imagePullPolicy": "Never", "command": ["python", "/fixture/personal_fixture.py"], "ports": [{"containerPort": 8443}], "readinessProbe": {"tcpSocket": {"port": 8443}, "periodSeconds": 2}, "volumeMounts": [{"name": "fixture", "mountPath": "/fixture", "readOnly": True}, {"name": "tls", "mountPath": "/tls", "readOnly": True}, {"name": "identity", "mountPath": "/identity", "readOnly": True}]}], "volumes": [{"name": "fixture", "configMap": {"name": "personal-runtime"}}, {"name": "tls", "secret": {"secretName": "personal-runtime-tls"}}, {"name": "identity", "secret": {"secretName": "personal-runtime-identity"}}]}}}})
    kubectl("rollout", "status", "deployment/personal-runtime", "--timeout=2m")
    fixture_pod = json.loads(kubectl("get", "pods", "-l", "app=personal-runtime", "-o", "json"))["items"][0]
    node = fixture_pod["spec"]["nodeName"]
    ip = fixture_pod["status"]["podIP"]
    subprocess.run(["docker", "exec", node, "iptables", "-t", "nat", "-I", "PREROUTING", "1", "-d", "93.184.216.34/32", "-p", "tcp", "--dport", "443", "-j", "DNAT", "--to-destination", f"{ip}:8443"], check=True, capture_output=True)
    pod["hostAliases"] = [{"ip": "93.184.216.34", "hostnames": ["personal-runtime.kind.invalid", "identity.personal-runtime.kind.invalid"]}]
    pod["volumes"].append({"name": "personal-ca", "configMap": {"name": "personal-runtime", "items": [{"key": "ca.crt", "path": "ca.crt"}]}})
    secondary = copy.deepcopy(primary)
    secondary["name"] = "mcp-b"
    secondary["env"] = [entry for entry in secondary["env"] if entry["name"] not in ("UMBOD_MCP_TEST_BEARER_TOKEN", "UMBOD_MCP_PORT", "UMBOD_MCP_METRICS_PORT", "PORT")]
    secondary["env"].extend([{"name": "UMBOD_MCP_PORT", "value": "8013"}, {"name": "UMBOD_MCP_METRICS_PORT", "value": "8014"}, {"name": "UMBOD_MCP_TEST_BEARER_TOKEN", "valueFrom": {"secretKeyRef": {"name": "umbod-ci", "key": "UMBOD_MCP_TEST_BEARER_TOKEN_B"}}}])
    secondary["ports"] = [{"name": "http-mcp-b", "containerPort": 8013}, {"name": "metrics-mcp-b", "containerPort": 8014}]
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        secondary[probe]["httpGet"]["port"] = "http-mcp-b"
    pod["containers"].append(secondary)
    secondary_api = copy.deepcopy(next(container for container in pod["containers"] if container["name"] == "api"))
    secondary_api["name"] = "api-b"
    secondary_api["env"] = [entry for entry in secondary_api["env"] if entry["name"] not in ("UMBOD_REST_PORT", "UMBOD_REST_METRICS_PORT", "PORT")]
    secondary_api["env"].extend([{"name": "UMBOD_REST_PORT", "value": "8015"}, {"name": "UMBOD_REST_METRICS_PORT", "value": "8016"}])
    secondary_api["ports"] = [{"name": "http-api-b", "containerPort": 8015}, {"name": "metrics-api-b", "containerPort": 8016}]
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        secondary_api[probe]["httpGet"]["port"] = "http-api-b"
    pod["containers"].append(secondary_api)
    for container in pod["containers"]:
        identity_environment = {"UMBOD_PROFILE": "production", "UMBOD_AUTH": "auth0", "UMBOD_OIDC_DOMAIN": "identity.personal-runtime.kind.invalid", "UMBOD_OIDC_CLIENT_ID": "kind-client", "UMBOD_OIDC_AUDIENCE": "kind-client", "UMBOD_OIDC_ISSUER_URL": "https://identity.personal-runtime.kind.invalid/", "UMBOD_ADMIN_MEMBERSHIP_CLAIM": "groups", "UMBOD_MCP_PERMISSION_CLAIM": "groups", "SSL_CERT_FILE": "/personal-ca/ca.crt", "UMBOD_PUBLIC_API_ORIGIN": "https://umbod-runtime.kind.invalid"}
        container["env"] = [entry for entry in container["env"] if entry["name"] not in (*identity_environment, "UMBOD_OIDC_CLIENT_SECRET", "UMBOD_MCP_TEST_BEARER_TOKEN")]
        container["env"].extend({"name": name, "value": value} for name, value in identity_environment.items())
        container["env"].append({"name": "UMBOD_OIDC_CLIENT_SECRET", "valueFrom": {"secretKeyRef": {"name": "personal-runtime-identity", "key": "client-secret"}}})
        container["volumeMounts"].append({"name": "personal-ca", "mountPath": "/personal-ca", "readOnly": True})
    if os.environ.get("UMBOD_TEST_CONTENT_BACKEND") == "s3":
        shared_names = {
            "UMBOD_FILESYSTEM_CONTENT_BACKEND", "UMBOD_FILESYSTEM_S3_BUCKET",
            "UMBOD_FILESYSTEM_S3_REGION", "UMBOD_FILESYSTEM_S3_ENDPOINT_URL",
            "UMBOD_FILESYSTEM_S3_PREFIX", "UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
        }
        expected = {entry["name"]: entry for entry in primary["env"] if entry["name"] in shared_names}
        if expected.keys() != shared_names or expected["UMBOD_FILESYSTEM_CONTENT_BACKEND"].get("value") != "s3":
            raise RuntimeError("S3 worker configuration is incomplete")
        for container in pod["containers"]:
            actual = {entry["name"]: entry for entry in container["env"] if entry["name"] in shared_names}
            if actual != expected:
                raise RuntimeError("S3 worker configuration must be shared by every API and MCP worker")
    kubectl("patch", "deployment", "umbod-core", "--type=json", "-p", json.dumps([{"op": "replace", "path": "/spec/template/spec", "value": pod}]))
    kubectl("rollout", "status", "deployment/umbod-core", "--timeout=3m")


if __name__ == "__main__":
    main()
