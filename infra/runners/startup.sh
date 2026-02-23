#!/usr/bin/env bash
# startup.sh - GitHub Actions runner lifecycle: register, run, deregister
#
# Expected environment variables (set via Container App Job env):
#   GITHUB_PAT                - GitHub PAT with org runner registration scope
#   GH_URL                    - GitHub org URL (e.g., https://github.com/lvlup-sw)
#   REGISTRATION_TOKEN_API_URL - API endpoint for registration token

set -euo pipefail

# ---------------------------------------------------------------------------
# Cleanup: deregister runner on exit (success, failure, or signal)
# ---------------------------------------------------------------------------
cleanup() {
  echo "Deregistering runner..."
  ./config.sh remove --token "${REG_TOKEN}" 2>/dev/null || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 1. Obtain a short-lived registration token via GitHub API
# ---------------------------------------------------------------------------
echo "Requesting registration token from ${REGISTRATION_TOKEN_API_URL}..."

REG_TOKEN=$(curl -sS -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github.v3+json" \
  "${REGISTRATION_TOKEN_API_URL}" \
  | jq -r '.token')

if [ -z "${REG_TOKEN}" ] || [ "${REG_TOKEN}" = "null" ]; then
  echo "ERROR: Failed to obtain registration token"
  exit 1
fi

echo "Registration token obtained."

# ---------------------------------------------------------------------------
# 2. Configure the runner (ephemeral = single job, then exit)
# ---------------------------------------------------------------------------
./config.sh \
  --url "${GH_URL}" \
  --token "${REG_TOKEN}" \
  --ephemeral \
  --unattended \
  --disableupdate \
  --name "azure-caj-$(hostname)" \
  --labels "self-hosted,linux,x64"

# ---------------------------------------------------------------------------
# 3. Start the runner (blocks until the job completes or is cancelled)
# ---------------------------------------------------------------------------
./run.sh
