#!/usr/bin/env bash
set -euo pipefail

chart=${1:?Usage: check-release-chart.sh CHART INFRA_DIRECTORY IMAGE_DIGEST}
infra=${2:?Missing infra directory}
digest=${3:?Missing expected image digest}
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
validation_dir=$(mktemp -d)
trap 'rm -rf "$validation_dir"' EXIT

echo "Validating production configuration from infra $(git -C "$infra" rev-parse HEAD)"
yq -e 'select(.kind == "HelmRelease" and .metadata.name == "wanderbound") | .spec.values' \
  "$infra/clusters/shire/apps/wanderbound/app-chart.yaml" > "$validation_dir/values.yaml"
yq -e '.image.repository == null and .image.tag == null and .image.digest == null' \
  "$validation_dir/values.yaml" > /dev/null
kubernetes_version=$(sed -n 's/.*kubernetes_version *= "v\([^"]*\)"/\1/p' "$infra/tofu/locals.tf")
: "${kubernetes_version:?Missing production Kubernetes version}"

helm lint --strict "$chart" --values "$validation_dir/values.yaml"
helm template wanderbound "$chart" --namespace wanderbound --kube-version "$kubernetes_version" \
  --values "$validation_dir/values.yaml" > "$validation_dir/rendered.yaml"
DIGEST="$digest" yq -e '
  select(.kind == "Deployment") | .spec.template.spec |
  (.containers + (.initContainers // [])) |
  all_c(.image == "ghcr.io/itay-raveh/wanderbound@" + strenv(DIGEST))
' "$validation_dir/rendered.yaml" > /dev/null
kubeconform -strict -summary -kubernetes-version "$kubernetes_version" "$validation_dir/rendered.yaml"
