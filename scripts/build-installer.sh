#!/usr/bin/env bash
# build-installer.sh — produce a self-extracting installer.
#
# Output: a single .sh file that, when run, extracts the writer-app source
# into a temp dir and invokes scripts/install.sh.
#
# Usage:  bash scripts/build-installer.sh [OUTPUT_PATH] [VERSION]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$REPO_ROOT/dist/writer-app-install.sh}"
VERSION="${2:-$(sed -n 's/^version *= *"\(.*\)"/\1/p' "$REPO_ROOT/pyproject.toml" | head -1)}"
WORKDIR="$(mktemp -d)"
PAYLOAD_TAR="$WORKDIR/writer-app.tar.gz"

trap 'rm -rf "$WORKDIR"' EXIT

mkdir -p "$(dirname "$OUTPUT")"

# ── Stage payload ────────────────────────────────────────────────────────
STAGING="$WORKDIR/writer-app-${VERSION}"
mkdir -p "$STAGING"
cp -R "$REPO_ROOT/src"          "$STAGING/"
cp -R "$REPO_ROOT/ui"           "$STAGING/"
cp -R "$REPO_ROOT/scripts"      "$STAGING/"
cp -R "$REPO_ROOT/docs"         "$STAGING/" 2>/dev/null || true
cp -R "$REPO_ROOT/corpus"       "$STAGING/" 2>/dev/null || true
cp -R "$REPO_ROOT/.streamlit"   "$STAGING/" 2>/dev/null || true
cp    "$REPO_ROOT/pyproject.toml" "$STAGING/"
cp    "$REPO_ROOT/README.md"      "$STAGING/"
cp    "$REPO_ROOT/LICENSE"        "$STAGING/"

# Strip __pycache__ and pyc
find "$STAGING" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type f -name '*.pyc'     -delete 2>/dev/null || true

# Drop the Gutenberg corpus from the installer payload — it's heavy and the
# user can download it later with `writer corpus`. Keep style cards + craft.
rm -rf "$STAGING/corpus/gutenberg" 2>/dev/null || true

# ── Tar it up ────────────────────────────────────────────────────────────
tar -czf "$PAYLOAD_TAR" -C "$WORKDIR" "writer-app-${VERSION}"

PAYLOAD_SIZE=$(wc -c < "$PAYLOAD_TAR" | tr -d ' ')

# ── Build the self-extracting stub ───────────────────────────────────────
STUB="$WORKDIR/stub.sh"
cat > "$STUB" <<EOF
#!/usr/bin/env bash
# writer-app self-extracting installer (version ${VERSION}).
#
# Run: bash $(basename "$OUTPUT")
#
# This script contains its payload as a base64-encoded tarball appended after
# the __ARCHIVE_BELOW__ marker.

set -euo pipefail

VERSION="${VERSION}"
echo
echo "writer-app v\${VERSION} installer"
echo

# Where the payload starts (line after __ARCHIVE_BELOW__)
ARCHIVE_LINE=\$(awk '/^__ARCHIVE_BELOW__$/ { print NR + 1; exit 0; }' "\$0")

TMP=\$(mktemp -d)
trap 'rm -rf "\$TMP"' EXIT

echo "Extracting to \$TMP …"
tail -n +"\$ARCHIVE_LINE" "\$0" | base64 -d | tar -xzf - -C "\$TMP"

PAYLOAD_DIR="\$TMP/writer-app-\${VERSION}"
if [ ! -d "\$PAYLOAD_DIR" ]; then
    echo "✗ Could not find extracted payload at \$PAYLOAD_DIR" >&2
    exit 1
fi

# Hand off to scripts/install.sh
export WRITER_APP_PAYLOAD_DIR="\$PAYLOAD_DIR"
exec bash "\$PAYLOAD_DIR/scripts/install.sh"

# Should not reach here
exit 1
__ARCHIVE_BELOW__
EOF

# ── Concatenate stub + base64 payload ────────────────────────────────────
{
    cat "$STUB"
    base64 < "$PAYLOAD_TAR"
} > "$OUTPUT"

chmod +x "$OUTPUT"

# ── Done ─────────────────────────────────────────────────────────────────
OUT_SIZE=$(wc -c < "$OUTPUT" | tr -d ' ')
echo "  ✓ Wrote $OUTPUT"
echo "    Version: $VERSION"
echo "    Payload: $(printf "%'d" "$PAYLOAD_SIZE") bytes"
echo "    Output:  $(printf "%'d" "$OUT_SIZE") bytes"
echo
echo "Test it with:"
echo "    bash $OUTPUT"
