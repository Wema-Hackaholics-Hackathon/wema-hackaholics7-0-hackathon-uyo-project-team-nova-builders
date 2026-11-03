#!/usr/bin/env bash
# Re-pack the SDKs from ../sdks into the demo's vendor folders, then refresh the lockfiles.
# Run it after changing an SDK; the demo itself never imports from ../sdks.
set -euo pipefail
DEMO="$(cd "$(dirname "$0")/.." && pwd)"
SDKS="$DEMO/../sdks"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

rm -f "$DEMO"/python/vendor/*.whl "$DEMO"/node/vendor/*.tgz "$DEMO"/vendor/*.tgz
(cd "$SDKS/python" && uv build --wheel -o "$TMP" >/dev/null) && cp "$TMP"/*.whl "$DEMO/python/vendor/"
(cd "$SDKS/node" && npm pack --silent --pack-destination "$DEMO/node/vendor" >/dev/null)
(cd "$SDKS/react" && npm pack --silent --pack-destination "$DEMO/vendor" >/dev/null)

(cd "$DEMO/python" && uv lock --refresh-package foid)
# Same version number, new contents: drop the old lock entry (its checksum) so npm takes the new tarball.
forget() {  # $1 = project dir, $2 = package name
  (cd "$1" && rm -rf "node_modules/$2" && node -e '
    const fs = require("fs"); const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
    delete lock.packages["node_modules/" + process.argv[1]];
    fs.writeFileSync("package-lock.json", JSON.stringify(lock, null, 2) + "\n");' "$2" \
    && npm install --no-audit --no-fund)
}
forget "$DEMO/node" @foid/node
forget "$DEMO" @foid/react
echo "Packed:"; ls "$DEMO"/python/vendor "$DEMO"/node/vendor "$DEMO"/vendor
