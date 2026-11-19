#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Installs the release this site's channel names once it passes the self-test.
#
# Reads channels/<site>.json from the release bucket. When that version is newer
# than the installed one, downloads releases/<version>/{release.json,release.json.sig,model.tar.gz},
# verifies them (verify_release.sh), runs the self-test on the unpacked release
# as user conveyor, and only then switches /opt/conveyor/model to the new version
# in one rename. A failed verification or self-test leaves the installed model in
# place, is recorded in state/fetch.json, which the local UI shows, and is retried
# on the next run. A channel naming an older version than the installed one is
# refused: a rollback needs a new, higher release of the older model.
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$BASE/env"
STATE="$BASE/state"
WORK="$BASE/fetch"
mkdir -p "$STATE"

exec 9>"$BASE/.fetch.lock"
flock 9

record() {
  python3.12 - "$STATE/fetch.json" "$1" "$2" "$3" <<'PY'
import json, sys
from datetime import datetime, timezone
path, version, status, detail = sys.argv[1:]
json.dump({"version": version, "status": status, "detail": detail,
           "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, open(path, "w"))
PY
}

if ! OUT=$(aws s3 cp "s3://$RELEASE_BUCKET/channels/$SITE.json" "$STATE/channel.json" --region "$REGION" --only-show-errors 2>&1); then
  # No channel yet is the normal state before the first approval.
  if grep -qE '404|NoSuchKey|Not Found' <<<"$OUT"; then
    record "" waiting "no release approved for this site yet"
    exit 0
  fi
  record "" error "$OUT"
  echo "$OUT" >&2
  exit 1
fi
VERSION=$(python3.12 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$STATE/channel.json")
if [[ ! "$VERSION" =~ ^v[0-9]+$ ]]; then
  record "$VERSION" rejected "channel names an invalid version"
  exit 1
fi
INSTALLED=$(readlink "$BASE/model" 2>/dev/null || true)
INSTALLED=${INSTALLED##*/model-v}
if [[ -n "$INSTALLED" ]]; then
  if (( ${VERSION#v} == INSTALLED )); then
    # Clears an earlier refusal once the channel names the installed release again.
    record "$VERSION" verified "release $VERSION already installed"
    echo "release $VERSION already installed"
    exit 0
  fi
  if (( ${VERSION#v} < INSTALLED )); then
    record "$VERSION" rejected "channel names $VERSION, older than the installed v$INSTALLED"
    exit 1
  fi
fi

rm -rf "$WORK" && mkdir -p "$WORK"
for object in release.json release.json.sig model.tar.gz; do
  aws s3 cp "s3://$RELEASE_BUCKET/releases/$VERSION/$object" "$WORK/$object" --region "$REGION" --only-show-errors
done
if ! DETAIL=$(bash "$BASE/bin/verify_release.sh" "$WORK/release.json" "$WORK/release.json.sig" \
    "$BASE/release-public-key.pem" "$WORK/model.tar.gz" "$VERSION" 2>&1); then
  record "$VERSION" rejected "$DETAIL"
  echo "$DETAIL" >&2
  exit 1
fi

STAGE="$BASE/model-$VERSION"
rm -rf "$STAGE" && mkdir -p "$STAGE"
tar -xzf "$WORK/model.tar.gz" -C "$STAGE" --no-same-owner
cp "$WORK/release.json" "$STAGE/release.json"
rm -rf "$WORK"
# Root never parses the new model or clips: the self-test runs as conveyor, and
# the running model is touched only once it passes.
if ! SELFTEST=$(env PYTHONPATH="$BASE/lib:$BASE/gateway" \
    setpriv --reuid=conveyor --regid=conveyor --init-groups --no-new-privs \
    python3.12 "$BASE/gateway/selftest.py" "$STAGE" 2>"$STATE/selftest.err"); then
  rm -rf "$STAGE"
  record "$VERSION" rejected "self-test failed: $(tail -n 3 "$STATE/selftest.err")"
  cat "$STATE/selftest.err" >&2
  exit 1
fi
ln -sfn "$STAGE" "$BASE/model.new"
mv -Tf "$BASE/model.new" "$BASE/model"
find "$BASE" -maxdepth 1 -type d -name 'model-v*' ! -name "model-$VERSION" -exec rm -rf {} +
printf '%s\n' "$SELFTEST" >"$STATE/selftest.json"
record "$VERSION" verified "$DETAIL"
systemctl restart conveyor-ui.service
echo "release $VERSION installed"
