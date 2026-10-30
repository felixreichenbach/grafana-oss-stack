#!/usr/bin/env bash
# Validate and deploy the Fleet Management pipelines in fleet/pipelines/.
#
# Each pipeline is a pair: <name>.alloy (the Alloy config) and <name>.json (spec name, enabled, matchers).
# Pipelines are created or updated by spec name, so the script is safe to re-run.
#
#   fleet/deploy.sh            validate + show what would change (no changes in Fleet)
#   fleet/deploy.sh --apply    validate + create/update the pipelines via gcx
#
# Requires: docker (for `alloy validate`), gcx logged in to the target stack, python3.
set -euo pipefail
cd "$(dirname "$0")/pipelines"

APPLY=false
[ "${1:-}" = "--apply" ] && APPLY=true
ALLOY_IMAGE="${ALLOY_IMAGE:-grafana/alloy:latest}"

# Dummy values so `alloy validate` can evaluate sys.env(...) without real credentials.
DUMMY_ENV=(
  -e LOKI_URL=http://localhost -e LOKI_USERNAME=1 -e GCLOUD_RW_API_KEY=x
  -e TEMPO_URL=http://localhost -e TEMPO_USERNAME=1
  -e S3_BUCKET=bucket -e S3_REGION=eu-central-1 -e S3_PREFIX=logs
)

for spec in *.json; do
  base="${spec%.json}"
  alloy_file="$base.alloy"
  name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$spec")"

  echo "==> $name ($alloy_file)"
  docker run --rm --entrypoint alloy "${DUMMY_ENV[@]}" \
    -v "$PWD/$alloy_file:/pipeline.alloy:ro" "$ALLOY_IMAGE" \
    validate --stability.level=experimental /pipeline.alloy
  echo "    validate: ok"

  existing="$(gcx fleet pipelines list -o json \
    --jq "[.[] | select(.spec.name==\"$name\") | .metadata.name]" \
    | python3 -c 'import json,sys; raw=sys.stdin.read(); v=json.loads(raw[raw.index("["):]); print(v[0] if v else "")')"

  manifest="$(python3 - "$spec" "$alloy_file" "$existing" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1]))
contents = open(sys.argv[2]).read()
manifest = {
    "apiVersion": "fleet.ext.grafana.app/v1alpha1",
    "kind": "Pipeline",
    "metadata": {"name": sys.argv[3]} if sys.argv[3] else {},
    "spec": {
        "name": spec["name"],
        "configType": "CONFIG_TYPE_ALLOY",
        "enabled": spec.get("enabled", True),
        "matchers": spec.get("matchers", []),
        "contents": contents,
    },
}
print(json.dumps(manifest))
PY
)"

  if [ -n "$existing" ]; then action="update $existing"; else action="create"; fi
  if [ "$APPLY" = true ]; then
    echo "    applying: $action"
    if [ -n "$existing" ]; then
      printf '%s' "$manifest" | gcx fleet pipelines update "$existing" -f -
    else
      printf '%s' "$manifest" | gcx fleet pipelines create -f -
    fi
  else
    echo "    dry run: would $action (matchers: $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("matchers"))' "$spec"))"
  fi
done
