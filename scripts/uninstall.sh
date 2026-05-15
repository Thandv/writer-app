#!/usr/bin/env bash
# Uninstall writer-app. Does NOT touch ~/books/ (your data).

set -euo pipefail

PREFIX="${WRITER_APP_PREFIX:-$HOME/.local/share/writer-app}"
BIN_DIR="${WRITER_APP_BIN:-$HOME/.local/bin}"

echo "Uninstalling writer-app"
echo "  Prefix : $PREFIX"
echo "  Bin    : $BIN_DIR/writer"

read -r -p "Continue? [y/N] " confirm
if [ "${confirm:-N}" != "y" ] && [ "${confirm:-N}" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

rm -rf "$PREFIX"
rm -f  "$BIN_DIR/writer"
echo "  ✓ Removed $PREFIX"
echo "  ✓ Removed $BIN_DIR/writer"
echo
echo "Your projects under ~/books/ and the corpus under"
echo "~/.local/share/writer-app/corpus/ were NOT touched. Delete them"
echo "manually if you want a clean slate."
