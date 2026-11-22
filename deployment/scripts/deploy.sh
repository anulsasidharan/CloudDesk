#!/usr/bin/env bash
# Usage: deploy.sh <aws|azure|gcp> <dev|staging|prod> [--auto-approve]
set -euo pipefail
cloud="${1:?cloud}"; env="${2:?environment}"; flag="${3:-}"
case "$cloud" in aws|azure|gcp) ;; *) echo "unknown cloud: $cloud"; exit 2;; esac
case "$env" in dev|staging|prod) ;; *) echo "unknown environment: $env"; exit 2;; esac
if [ "$flag" = "--auto-approve" ] && [ "$env" != "dev" ]; then
  echo "--auto-approve is refused for $env"; exit 3
fi
dir="$(dirname "$0")/../$cloud"
terraform -chdir="$dir" init -backend-config=backend.hcl
terraform -chdir="$dir" plan -var-file="environments/$env/terraform.tfvars" -out=tfplan
[ "$flag" = "--auto-approve" ] && terraform -chdir="$dir" apply tfplan || {
  read -r -p "Apply this plan to $cloud/$env? type yes: " answer
  [ "$answer" = "yes" ] && terraform -chdir="$dir" apply tfplan
}
