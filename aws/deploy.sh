#!/usr/bin/env bash
# Deploy the AWS resources for the S3 log archive (aws/s3-log-archive.yaml) with CloudFormation.
#
#   aws/deploy.sh               dry run: lint the template and show the account, region and parameters
#   aws/deploy.sh --apply       create/update the stack
#   aws/deploy.sh --write-env   copy the stack's access key and bucket settings into .env.cloud
#                               (the secret key is read from Secrets Manager and never printed)
#
# Parameters come from .env.cloud (S3_BUCKET, S3_PREFIX, S3_REGION) so the stack and Alloy use the same values.
# Optional environment: AWS_PROFILE (default: default), STACK_NAME (default: alloy-s3-log-archive),
# RETENTION_DAYS (default: 0 = keep forever).
# Requires: aws CLI logged in (aws login), python3, uv (for cfn-lint).
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-dry-run}"
ENV_FILE=".env.cloud"
STACK_NAME="${STACK_NAME:-alloy-s3-log-archive}"
RETENTION_DAYS="${RETENTION_DAYS:-0}"
export AWS_PROFILE="${AWS_PROFILE:-default}"

# Read a KEY=value from .env.cloud without sourcing it.
env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true; }

BUCKET="$(env_value S3_BUCKET)"
PREFIX="$(env_value S3_PREFIX)"; PREFIX="${PREFIX:-logs}"
REGION="$(env_value S3_REGION)"
case "$BUCKET$REGION" in *YOUR_*|"") echo "Set S3_BUCKET and S3_REGION in $ENV_FILE first." >&2; exit 1;; esac

if [ "$MODE" = "--write-env" ]; then
  SECRET_ARN="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='AccessKeySecretArn'].OutputValue" --output text)"
  aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --region "$REGION" \
    --query SecretString --output text | python3 -c '
import json, re, sys
secret = json.load(sys.stdin)
path = ".env.cloud"
text = open(path).read()
for key, value in secret.items():
    if re.search(rf"^{key}=", text, re.M):
        text = re.sub(rf"^{key}=.*$", lambda m: f"{key}={value}", text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{key}={value}\n"
open(path, "w").write(text)
print("Updated AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env.cloud")'
  exit 0
fi

echo "==> Lint aws/s3-log-archive.yaml"
uvx --quiet cfn-lint aws/s3-log-archive.yaml
echo "    lint: ok"

echo "==> Target"
aws sts get-caller-identity --query '[Account,Arn]' --output text | sed 's/^/    account\/identity: /'
echo "    region: $REGION   stack: $STACK_NAME"
echo "    BucketName=$BUCKET Prefix=$PREFIX RetentionDays=$RETENTION_DAYS"

if [ "$MODE" = "--apply" ]; then
  echo "==> Deploying"
  aws cloudformation deploy \
    --stack-name "$STACK_NAME" --region "$REGION" \
    --template-file aws/s3-log-archive.yaml \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "BucketName=$BUCKET" "Prefix=$PREFIX" "RetentionDays=$RETENTION_DAYS" \
    --no-fail-on-empty-changeset
  echo "Done. Run aws/deploy.sh --write-env to copy the access key into $ENV_FILE."
else
  echo "Dry run only. Use --apply to create or update the stack."
fi
