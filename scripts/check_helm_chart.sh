#!/bin/sh
set -eu

chart=charts/wanderbound

helm lint --strict "$chart"

defaults="$(helm template wanderbound "$chart" --show-only templates/deployment.yaml)"
echo "$defaults" | grep -Fq '  replicas: 1'
echo "$defaults" | grep -Fq '    type: Recreate'

overrides="$(
  helm template wanderbound "$chart" \
    --show-only templates/deployment.yaml \
    --set replicaCount=3 \
    --set deploymentStrategy.type=RollingUpdate \
    --set deploymentStrategy.rollingUpdate.maxSurge=1 \
    --set deploymentStrategy.rollingUpdate.maxUnavailable=0
)"
echo "$overrides" | grep -Fq '  replicas: 3'
echo "$overrides" | grep -Fq '    type: RollingUpdate'
echo "$overrides" | grep -Fq '      maxSurge: 1'
echo "$overrides" | grep -Fq '      maxUnavailable: 0'
