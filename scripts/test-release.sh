#!/usr/bin/env bash
set -euo pipefail

test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
cat > "$test_dir/gh" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$CI_RESPONSE"
SH
chmod +x "$test_dir/gh"
revision=$(git rev-parse HEAD)
export GITHUB_REPOSITORY=itay-raveh/wanderbound
export CI_RESPONSE
CI_RESPONSE=$(jq -n --arg revision "$revision" '{workflow_runs: [{
  head_sha: $revision, head_branch: "main", event: "push", status: "completed", conclusion: "success"
}]}')
PATH="$test_dir:$PATH" bash scripts/check-release-ci.sh
success=$CI_RESPONSE
for mutation in '.workflow_runs = []' '.workflow_runs[0].head_sha = "other"' \
  '.workflow_runs[0].head_branch = "feature"' '.workflow_runs[0].event = "pull_request"' \
  '.workflow_runs[0].status = "in_progress"' '.workflow_runs[0].conclusion = "failure"' \
  '.workflow_runs[0].conclusion = "cancelled"'; do
  CI_RESPONSE=$(jq "$mutation" <<< "$success")
  if PATH="$test_dir:$PATH" bash scripts/check-release-ci.sh 2> /dev/null; then
    echo "CI gate accepted invalid release: $mutation" >&2
    exit 1
  fi
done

digest="sha256:$(printf '%064d' 1)"
cp -R charts/wanderbound "$test_dir/chart"
IMAGE_DIGEST="$digest" yq -i '.image.digest = strenv(IMAGE_DIGEST)' "$test_dir/chart/values.yaml"
helm package "$test_dir/chart" --destination "$test_dir" > /dev/null
chart="$test_dir/wanderbound-$(yq '.version' "$test_dir/chart/Chart.yaml").tgz"
helm template wanderbound "$chart" \
  --set-string image.tag=ignored --set sourceMaps.enabled=true --set sourceMaps.existingSecret=sourcemaps \
  > "$test_dir/rendered.yaml"
DIGEST="$digest" yq -e 'select(.kind == "Deployment") | .spec.template.spec |
  (.containers + .initContainers) | all_c(.image == "ghcr.io/itay-raveh/wanderbound@" + strenv(DIGEST))' \
  "$test_dir/rendered.yaml" > /dev/null
if helm template wanderbound charts/wanderbound --set-string image.digest=invalid > /dev/null 2>&1; then
  echo "Chart accepted an invalid image digest" >&2
  exit 1
fi

cat > "$test_dir/curl" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *'/token?'* ]]; then
  printf '{"token":"test"}\n'
else
  printf '%s' "$MANIFEST_STATUS"
fi
SH
chmod +x "$test_dir/curl"
PATH="$test_dir:$PATH" MANIFEST_STATUS=404 bash scripts/check-release-version.sh 1.16.1
for status in 200 401 403 429 500 000; do
  if PATH="$test_dir:$PATH" MANIFEST_STATUS="$status" bash scripts/check-release-version.sh 1.16.1 2> /dev/null; then
    echo "Version gate accepted unsafe manifest lookup: $status" >&2
    exit 1
  fi
done
echo "Release contracts passed"
