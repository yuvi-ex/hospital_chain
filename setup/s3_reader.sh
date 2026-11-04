#!/usr/bin/env bash
# Create the READ-ONLY IAM user Exasol and the console use to read the imaging bucket. setup/build_all.sh runs it
# (step 7) unless HC_S3_KEY_FILE already holds a key, so you can also bring your own read-only key in that JSON shape.
# Grants GetObject + ListBucket on this demo's part of ONE bucket (HC_S3_PREFIX), nothing else. The key lands in
# HC_S3_KEY_FILE (mode 600). It is long-lived: setup/uninstall.sh --yes --aws deletes it with the user.
# Needs an AWS profile allowed to: iam:GetUser, CreateUser, TagUser, PutUserPolicy, CreateAccessKey.
source "$(dirname "$0")/common.sh"
export AWS_PROFILE="${HC_AWS_PROFILE:-default}"
B="$S3_BUCKET"
U="$HC_CONTAINER_PREFIX-s3-reader"
OUT="$S3_KEY_FILE"
mkdir -p "$(dirname "$OUT")"

aws iam get-user --user-name "$U" >/dev/null 2>&1 || \
  aws iam create-user --user-name "$U" --tags Key=project,Value=hospital-chain-demo >/dev/null
printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::%s/%s*"},{"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::%s","Condition":{"StringLike":{"s3:prefix":["%s*"]}}},{"Effect":"Allow","Action":["s3:GetBucketLocation"],"Resource":"arn:aws:s3:::%s"}]}' "$B" "$S3_PREFIX" "$B" "$S3_PREFIX" "$B" \
  | aws iam put-user-policy --user-name "$U" --policy-name hc-read-only --policy-document file:///dev/stdin
if [[ -s "$OUT" ]]; then echo "key already in $OUT"; exit 0; fi
umask 077
aws iam create-access-key --user-name "$U" --output json > "$OUT"
echo "ok: read-only key for $B written to $OUT"
