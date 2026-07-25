# Wanderbound Helm chart

The chart installs one Wanderbound pod, a ClusterIP Service, and a persistent
volume. You provide PostgreSQL, object storage, ingress, TLS, and backups.

## Prerequisites

- Helm 3.8 or newer
- A PostgreSQL database
- A Kubernetes namespace and Secret for Wanderbound

## Install

Create the namespace and Secret:

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

Access the service without Ingress:

```bash
kubectl --namespace wanderbound port-forward service/wanderbound 8000:8000
```

## Configuration

`DATA_FOLDER` is fixed to `/data` and cannot be set through `config`. Use
[`.env.example`](../../.env.example) as the application setting reference.

`existingSecrets` imports complete Secrets with `envFrom`. Use `secretEnv` to
map one environment variable to a Secret key:

```yaml
secretEnv:
  SQLALCHEMY_DATABASE_URI:
    secretName: application-database
    key: uri
```

The managed PVC defaults to `10Gi`, `ReadWriteOnce`, and the cluster's default
storage class. Set `persistence.existingClaim` to use an existing PVC.

See [`values.yaml`](values.yaml) for all values and
[`values.schema.json`](values.schema.json) for validation rules.
