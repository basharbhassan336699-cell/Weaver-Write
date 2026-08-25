#!/usr/bin/env bash
# One-time helper to publish Weaver Write to GitHub
set -e
cd "$(dirname "$0")"

USERNAME="${1:-basharbhassan336699-cell}"
REPO="Weaver-Write"

echo "Publishing Weaver Write to github.com/$USERNAME/$REPO ..."

git init 2>/dev/null || true
git add -A
git commit -m "Weaver Write — initial release" || echo "(nothing to commit)"
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$USERNAME/$REPO.git"

echo ""
echo "Now create an empty repo named '$REPO' on GitHub, then run:"
echo "    git push -u origin main"
