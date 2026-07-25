from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "wanderbound"
RELEASE = "wanderbound"
NAMESPACE = "wanderbound"


def run(*args: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if not expect_success and result.returncode == 0:
        raise AssertionError(f"command unexpectedly passed: {' '.join(args)}")
    return result


def values_file(values: dict[str, Any]) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="wanderbound-values-", delete=False
    )
    with handle:
        yaml.safe_dump(values, handle, sort_keys=False)
    return Path(handle.name)


def render(values: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    args = [
        "helm",
        "template",
        RELEASE,
        str(CHART),
        "--namespace",
        NAMESPACE,
    ]
    path: Path | None = None
    if values is not None:
        path = values_file(values)
        args.extend(("--values", str(path)))
    try:
        result = run(*args)
    finally:
        if path is not None:
            path.unlink()
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def expect_invalid(values: dict[str, Any]) -> None:
    path = values_file(values)
    try:
        run(
            "helm",
            "template",
            RELEASE,
            str(CHART),
            "--namespace",
            NAMESPACE,
            "--values",
            str(path),
            expect_success=False,
        )
    finally:
        path.unlink()


def resource(
    documents: Iterable[dict[str, Any]], kind: str, name: str
) -> dict[str, Any]:
    matches = [
        item
        for item in documents
        if item.get("kind") == kind and item.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1, f"expected one {kind}/{name}, found {len(matches)}"
    return matches[0]


def container(
    pod_spec: dict[str, Any], name: str, *, init: bool = False
) -> dict[str, Any]:
    key = "initContainers" if init else "containers"
    matches = [item for item in pod_spec.get(key, []) if item.get("name") == name]
    assert len(matches) == 1, f"expected one {key} entry named {name}"
    return matches[0]


def env_value(container_spec: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [
        item for item in container_spec.get("env", []) if item.get("name") == name
    ]
    assert len(matches) == 1, f"expected one environment entry named {name}"
    return matches[0]


def assert_security_context(context: dict[str, Any]) -> None:
    assert context == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "readOnlyRootFilesystem": True,
        "runAsGroup": 999,
        "runAsNonRoot": True,
        "runAsUser": 999,
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def assert_default_render() -> None:
    documents = render()
    kinds = {item["kind"] for item in documents}
    assert kinds == {"ConfigMap", "Deployment", "PersistentVolumeClaim", "Service"}

    config = resource(documents, "ConfigMap", "wanderbound-config")
    assert config["metadata"]["namespace"] == NAMESPACE
    assert config["data"] == {"DATA_FOLDER": "/data"}

    deployment = resource(documents, "Deployment", "wanderbound")
    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"] == {"type": "Recreate"}
    assert deployment["spec"]["selector"]["matchLabels"] == {"app": "wanderbound"}
    template = deployment["spec"]["template"]
    assert template["metadata"]["labels"]["app"] == "wanderbound"
    assert template["metadata"]["annotations"]["checksum/config"]
    pod_spec = template["spec"]
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"] == {"fsGroup": 999}
    assert "initContainers" not in pod_spec

    app = container(pod_spec, "wanderbound")
    assert app["image"] == "ghcr.io/itay-raveh/wanderbound:1.9.0"
    assert app["imagePullPolicy"] == "IfNotPresent"
    assert app["resources"] == {}
    assert "command" not in app
    assert "args" not in app
    assert app["envFrom"] == [{"configMapRef": {"name": "wanderbound-config"}}]
    assert "env" not in app
    assert_security_context(app["securityContext"])
    assert app["startupProbe"] == {
        "failureThreshold": 30,
        "httpGet": {"path": "/api/v1/health", "port": 8000},
        "periodSeconds": 2,
    }
    assert app["readinessProbe"]["periodSeconds"] == 5
    assert app["livenessProbe"]["periodSeconds"] == 15
    assert {item["mountPath"] for item in app["volumeMounts"]} == {
        "/data",
        "/dev/shm",
        "/tmp",
    }
    volumes = {item["name"]: item for item in pod_spec["volumes"]}
    assert volumes["app-data"]["persistentVolumeClaim"]["claimName"] == (
        "wanderbound-app-data"
    )
    assert volumes["dshm"]["emptyDir"] == {"medium": "Memory", "sizeLimit": "256Mi"}
    assert volumes["tmp"]["emptyDir"] == {}

    service = resource(documents, "Service", "wanderbound")
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["selector"] == {"app": "wanderbound"}
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 8000, "protocol": "TCP", "targetPort": 8000}
    ]

    pvc = resource(documents, "PersistentVolumeClaim", "wanderbound-app-data")
    assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    assert pvc["spec"] == {
        "accessModes": ["ReadWriteOnce"],
        "resources": {"requests": {"storage": "10Gi"}},
    }


def assert_configured_render() -> None:
    values = {
        "image": {
            "repository": "registry.example/wanderbound",
            "tag": "2.4.6",
            "pullPolicy": "Always",
        },
        "config": {
            "PUBLIC_URL": "https://photos.example.test",
            "ENVIRONMENT": "production",
            "WORKER_THREADS": 3,
            "FEATURE_ENABLED": True,
        },
        "existingSecrets": ["wanderbound-secrets", "upload-secrets"],
        "secretEnv": {
            "SQLALCHEMY_DATABASE_URI": {
                "secretName": "wanderbound-db-app",
                "key": "uri",
            }
        },
        "resources": {
            "requests": {"cpu": "250m", "memory": "512Mi"},
            "limits": {"cpu": "2", "memory": "2Gi"},
        },
        "persistence": {"existingClaim": "photos-data"},
        "ingress": {
            "enabled": True,
            "className": "nginx",
            "annotations": {"example.test/setting": "enabled"},
            "host": "photos.example.test",
            "tls": [
                {
                    "secretName": "photos-tls",
                    "hosts": ["photos.example.test"],
                }
            ],
        },
        "sourceMaps": {
            "enabled": True,
            "existingSecret": "sentry-upload",
        },
    }
    documents = render(values)
    assert "PersistentVolumeClaim" not in {item["kind"] for item in documents}

    config = resource(documents, "ConfigMap", "wanderbound-config")
    assert config["data"] == {
        "DATA_FOLDER": "/data",
        "ENVIRONMENT": "production",
        "FEATURE_ENABLED": "true",
        "PUBLIC_URL": "https://photos.example.test",
        "WORKER_THREADS": "3",
    }

    deployment = resource(documents, "Deployment", "wanderbound")
    pod_spec = deployment["spec"]["template"]["spec"]
    app = container(pod_spec, "wanderbound")
    assert app["image"] == "registry.example/wanderbound:2.4.6"
    assert app["imagePullPolicy"] == "Always"
    assert app["envFrom"] == [
        {"configMapRef": {"name": "wanderbound-config"}},
        {"secretRef": {"name": "wanderbound-secrets"}},
        {"secretRef": {"name": "upload-secrets"}},
    ]
    assert env_value(app, "SQLALCHEMY_DATABASE_URI")["valueFrom"] == {
        "secretKeyRef": {"key": "uri", "name": "wanderbound-db-app"}
    }
    assert app["resources"] == values["resources"]
    app_data = next(item for item in pod_spec["volumes"] if item["name"] == "app-data")
    assert app_data["persistentVolumeClaim"]["claimName"] == "photos-data"

    source_maps = container(pod_spec, "sourcemaps", init=True)
    assert [item["name"] for item in pod_spec["initContainers"]] == ["sourcemaps"]
    assert source_maps["image"] == "registry.example/wanderbound:2.4.6"
    assert source_maps["command"] == ["/usr/local/bin/upload-sourcemaps"]
    assert source_maps["envFrom"] == [
        {"configMapRef": {"name": "wanderbound-config"}},
        {"secretRef": {"name": "sentry-upload"}},
    ]
    assert env_value(source_maps, "HOME")["value"] == "/tmp"
    assert env_value(source_maps, "SENTRY_DISABLE_UPDATE_CHECK")["value"] == "true"
    assert_security_context(source_maps["securityContext"])

    ingress = resource(documents, "Ingress", "wanderbound")
    assert ingress["apiVersion"] == "networking.k8s.io/v1"
    assert ingress["metadata"]["annotations"] == {"example.test/setting": "enabled"}
    assert ingress["spec"]["ingressClassName"] == "nginx"
    assert ingress["spec"]["rules"][0]["host"] == "photos.example.test"
    path = ingress["spec"]["rules"][0]["http"]["paths"][0]
    assert path["path"] == "/"
    assert path["pathType"] == "Prefix"
    assert path["backend"]["service"] == {
        "name": "wanderbound",
        "port": {"number": 8000},
    }
    assert ingress["spec"]["tls"] == values["ingress"]["tls"]


def assert_persistence_options() -> None:
    documents = render(
        {
            "persistence": {
                "size": "50Gi",
                "storageClass": "fast-storage",
                "accessModes": ["ReadWriteMany"],
                "retain": False,
            }
        }
    )
    pvc = resource(documents, "PersistentVolumeClaim", "wanderbound-app-data")
    assert "annotations" not in pvc["metadata"]
    assert pvc["spec"] == {
        "accessModes": ["ReadWriteMany"],
        "resources": {"requests": {"storage": "50Gi"}},
        "storageClassName": "fast-storage",
    }


def assert_invalid_values() -> None:
    expect_invalid({"config": {"DATA_FOLDER": "/somewhere-else"}})
    expect_invalid({"existingSecrets": [{"name": "not-a-string"}]})
    expect_invalid({"secretEnv": {"DATABASE_URL": {"secretName": "db"}}})
    expect_invalid({"persistence": {"size": ""}})
    expect_invalid(
        {
            "ingress": {
                "enabled": True,
                "host": "photos.example.test",
                "tls": [{"hosts": ["photos.example.test"]}],
            }
        }
    )


def assert_installation_neutral() -> None:
    forbidden = (
        "raveh.dev",
        "hcloud",
        "cloudnative-pg",
        "cnpg",
        "traefik",
        "fluxcd",
        "your-objectstorage.com",
    )
    for path in CHART.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text().lower()
        for token in forbidden:
            assert token not in content, f"{path.relative_to(ROOT)} contains {token!r}"


def assert_metadata() -> None:
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "wanderbound"
    assert chart["type"] == "application"
    assert chart["version"] == "1.9.0"
    assert str(chart["appVersion"]) == "1.9.0"
    schema = json.loads((CHART / "values.schema.json").read_text())
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"


def assert_documentation() -> None:
    chart_readme = (CHART / "README.md").read_text()
    root_readme = (ROOT / "README.md").read_text()
    for text in (chart_readme, root_readme):
        assert "oci://ghcr.io/itay-raveh/charts/wanderbound" in text
    assert ".env.example" in chart_readme
    assert "does not install a database" in chart_readme
    assert "existingSecrets" in chart_readme
    assert "secretEnv" in chart_readme
    assert "existingClaim" in chart_readme
    assert "sourceMaps" in chart_readme
    assert "Self-Hosting on Kubernetes" in root_readme


def assert_workflows() -> None:
    ci_path = ROOT / ".github" / "workflows" / "ci.yml"
    publish_path = ROOT / ".github" / "workflows" / "publish.yml"
    yaml.safe_load(ci_path.read_text())
    yaml.safe_load(publish_path.read_text())

    ci = ci_path.read_text()
    assert "charts/wanderbound/**" in ci
    assert "mise run test:helm" in ci
    assert "install_args: python uv helm" in ci

    publish = publish_path.read_text()
    image_push = publish.index(
        'docker push "$APP_IMAGE:${{ steps.version.outputs.value }}"'
    )
    chart_package = publish.index("helm package charts/wanderbound")
    chart_push = publish.index("helm push")
    assert image_push < chart_package < chart_push
    assert '--version "${{ steps.version.outputs.value }}"' in publish
    assert '--app-version "${{ steps.version.outputs.value }}"' in publish
    assert "oci://ghcr.io/itay-raveh/charts" in publish


def main() -> None:
    assert CHART.is_dir(), f"chart directory does not exist: {CHART}"
    run("helm", "lint", str(CHART), "--strict")
    assert_metadata()
    assert_default_render()
    assert_configured_render()
    assert_persistence_options()
    assert_invalid_values()
    assert_installation_neutral()
    assert_documentation()
    assert_workflows()
    print("Helm chart contract passed")


if __name__ == "__main__":
    main()
