#!/bin/sh
set -eu

: "${UPLOAD_S3_BUCKET:?Variable not set}"
: "${UPLOAD_CORS_ORIGIN:?Variable not set}"

cors_file=$(mktemp)
lifecycle_file=$(mktemp)
trap 'rm -f "$cors_file" "$lifecycle_file"' EXIT

cat >"$cors_file" <<EOF
{
  "CORSRules": [
    {
      "AllowedOrigins": ["${UPLOAD_CORS_ORIGIN}"],
      "AllowedMethods": ["PUT"],
      "AllowedHeaders": ["content-type", "x-amz-content-sha256"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3600
    }
  ]
}
EOF

cat >"$lifecycle_file" <<'EOF'
{
  "Rules": [
    {
      "ID": "abort-incomplete-uploads",
      "Status": "Enabled",
      "Filter": {},
      "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}
    },
    {
      "ID": "expire-completed-uploads",
      "Status": "Enabled",
      "Filter": {"Prefix": "uploads/"},
      "Expiration": {"Days": 3}
    }
  ]
}
EOF

aws s3api put-bucket-cors \
  --bucket "$UPLOAD_S3_BUCKET" \
  --cors-configuration "file://$cors_file"
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$UPLOAD_S3_BUCKET" \
  --lifecycle-configuration "file://$lifecycle_file"

attempt=0
until aws s3api get-bucket-cors --bucket "$UPLOAD_S3_BUCKET" >/dev/null 2>&1 \
  && aws s3api get-bucket-lifecycle-configuration \
    --bucket "$UPLOAD_S3_BUCKET" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "bucket configuration was not readable after 30 attempts" >&2
    exit 1
  fi
  sleep 1
done

aws s3api head-bucket --bucket "$UPLOAD_S3_BUCKET"
