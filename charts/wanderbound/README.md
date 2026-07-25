# Wanderbound Helm chart

This chart runs one Wanderbound application pod with a Service and persistent
application-data volume. It is intended as a short path to a homelab install and
as a reusable application building block for operators who manage the rest of
their stack themselves.

## Prerequisites

- Kubernetes
- Helm 3.8 or newer
- A PostgreSQL database
- Any external services required by the settings you enable

The chart does not create a namespace. It also does not install a database,
object storage, backup tooling, an ingress controller, certificates, or
cluster policy.

## Install

Create the namespace and a Secret containing the required private application
settings. Replace every placeholder before running these commands.

```bash
kubectl create namespace wanderbound
kubectl --namespace wanderbound create secret generic wanderbound-secrets \
  --from-literal=SECRET_KEY='<YOUR_SECRET_KEY>' \
  --from-literal=SQLALCHEMY_DATABASE_URI='<YOUR_POSTGRESQL_URI>'
```

Create `values.yaml`:

```yaml
config:
  ENVIRONMENT: production
  PUBLIC_URL: https://wanderbound.example.com

existingSecrets:
  - wanderbound-secrets

persistence:
  size: 20Gi

ingress:
  enabled: true
  className: nginx
  host: wanderbound.example.com
  tls:
    - secretName: wanderbound-tls
      hosts:
        - wanderbound.example.com
```

Install an exact release:

```bash
WANDERBOUND_VERSION='<MAJOR.MINOR.PATCH>'
helm install wanderbound \
  oci://ghcr.io/itay-raveh/charts/wanderbound \
  --namespace wanderbound \
  --version "$WANDERBOUND_VERSION" \
  --values values.yaml
```

If Ingress is disabled, access the service locally with:

```bash
kubectl --namespace wanderbound port-forward service/wanderbound 8000:8000
```

## Values

The values surface is intentionally small.

| Value | Purpose | Default |
| --- | --- | --- |
| `image.repository` | Wanderbound image repository | `ghcr.io/itay-raveh/wanderbound` |
| `image.tag` | Exact image tag, or chart `appVersion` when empty | `""` |
| `image.pullPolicy` | Kubernetes image pull policy | `IfNotPresent` |
| `config` | Non-secret Wanderbound environment settings | `{}` |
| `existingSecrets` | Secrets imported with `envFrom` | `[]` |
| `secretEnv` | Individual environment variables sourced from Secret keys | `{}` |
| `resources` | Application container requests and limits | `{}` |
| `persistence.existingClaim` | Existing PVC to mount instead of creating one | `""` |
| `persistence.size` | Size of the managed PVC | `10Gi` |
| `persistence.storageClass` | Storage class, or the cluster default when empty | `""` |
| `persistence.accessModes` | Managed PVC access modes | `[ReadWriteOnce]` |
| `persistence.retain` | Keep the managed PVC when Helm removes the release | `true` |
| `ingress` | Optional standard Kubernetes Ingress | disabled |
| `sourceMaps` | Optional source-map upload init container using an existing Secret | disabled |

`DATA_FOLDER` is fixed to `/data` and cannot be set through `config`. For the
available application settings, required values, and examples, use the
repository's [`.env.example`](../../.env.example) as the canonical reference.

Use `secretEnv` when an operator-created Secret has a key name that differs from
the environment variable Wanderbound expects:

```yaml
secretEnv:
  SQLALCHEMY_DATABASE_URI:
    secretName: application-database
    key: uri
```

Set `sourceMaps.enabled: true` only when the application image contains the
source-map uploader and `sourceMaps.existingSecret` names a Secret with its
credentials. A failed upload blocks application startup so a broken release is
visible immediately.

The chart deliberately omits generic resource injection, scheduling knobs, and
provider-specific resources. Operators can manage or patch the rendered
resources with their normal deployment tooling.
