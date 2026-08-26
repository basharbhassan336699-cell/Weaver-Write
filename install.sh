#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# Weaver Write — installer (Linux / macOS / Termux-Android)
# ═══════════════════════════════════════════════════════════
set -e

REPO="https://github.com/basharbhassan336699-cell/Weaver-Write.git"
INSTALL_DIR="${WEAVER_HOME:-$HOME/weaver-write}"

echo "═══════════════════════════════════════"
echo "   Weaver Write — Installer"
echo "═══════════════════════════════════════"

# 1. detect platform
if [ -n "$TERMUX_VERSION" ] || echo "$PREFIX" | grep -q "com.termux"; then
    PLATFORM="termux"
elif [ "$(uname)" = "Darwin" ]; then
    PLATFORM="macos"
else
    PLATFORM="linux"
fi
echo "Platform detected: $PLATFORM"

# 2. ensure python + git
ensure_pkg() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Installing $1..."
        case "$PLATFORM" in
            termux) pkg install -y "$2" ;;
            macos)  brew install "$2" ;;
            linux)  sudo apt-get install -y "$2" ;;
        esac
    fi
}
ensure_pkg python3 python
ensure_pkg git git

# 3. clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing install..."
    # ignore file-mode (chmod +x) differences so updates never conflict, and
    # hard-reset to the remote so a local mode/edit can't abort the update
    git -C "$INSTALL_DIR" config core.fileMode false 2>/dev/null || true
    git -C "$INSTALL_DIR" fetch origin main --quiet 2>/dev/null || git -C "$INSTALL_DIR" fetch origin --quiet
    git -C "$INSTALL_DIR" reset --hard origin/main 2>/dev/null || git -C "$INSTALL_DIR" pull --ff-only
else
    echo "Cloning Weaver Write..."
    git clone "$REPO" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
# don't let a later `chmod +x` register as a tracked change
git config core.fileMode false 2>/dev/null || true

# 4. python deps
echo "Installing Python libraries..."
if [ "$PLATFORM" = "termux" ]; then
    # NOTE: on Termux, `pip install --upgrade pip` is forbidden — it breaks the
    # python-pip package. Also, compiled libraries (numpy/scipy/pandas/matplotlib)
    # must come from Termux prebuilt packages; building them from pip source needs
    # ninja/cmake and fails on-device (e.g. "matplotlib" / "ninja" build errors).
    pkg install -y python-pip 2>/dev/null || true
    pkg install -y matplotlib python-numpy python-pandas python-scipy python-pillow 2>/dev/null || true
    # matplotlib from pkg satisfies the pin, so pip skips it and its small
    # pure-python runtime deps. Install those explicitly (fast, no compilation)
    # so matplotlib imports cleanly and pip stops warning about missing deps.
    pip install cycler fonttools kiwisolver pyparsing packaging python-dateutil 2>/dev/null || true
    # Install each requirement independently so one heavy package that cannot
    # build on-device (e.g. torch-based paper-qa) does not abort the rest.
    grep -vE '^[[:space:]]*#|^[[:space:]]*$' requirements.txt | while IFS= read -r req; do
        pip install "$req" 2>/dev/null || echo "  skipped (optional / needs compilation): $req"
    done
else
    python3 -m pip install --upgrade pip --break-system-packages 2>/dev/null || python3 -m pip install --upgrade pip
    python3 -m pip install -r requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r requirements.txt
fi

# 5. optional system tools (OCR, node for html2pptx)
echo "Installing optional tools (OCR, node)..."
case "$PLATFORM" in
    termux) pkg install -y tesseract nodejs || true ;;
    macos)  brew install tesseract node || true ;;
    linux)  sudo apt-get install -y tesseract-ocr nodejs npm || true ;;
esac

# 6. html2pptx node deps
if [ -d "engines/html2pptx-core" ]; then
    (cd engines/html2pptx-core && npm install --silent adm-zip cheerio css pptxgenjs) || true
fi

# 7. make CLI available
# Use a wrapper script that calls `python3 weaver.py` rather than a symlink to
# weaver.py — a symlink depends on the file's exec bit, which can get lost on
# some devices/filesystems and cause "Permission denied" when running `weaver`.
chmod +x weaver.py 2>/dev/null || true
_wrapper="#!/usr/bin/env bash
exec python3 \"$INSTALL_DIR/weaver.py\" \"\$@\""
if printf '%s\n' "$_wrapper" > "$PREFIX/bin/weaver" 2>/dev/null; then
    chmod +x "$PREFIX/bin/weaver"
elif printf '%s\n' "$_wrapper" | sudo tee /usr/local/bin/weaver >/dev/null 2>&1; then
    sudo chmod +x /usr/local/bin/weaver
else
    echo "Add to PATH manually: alias weaver='python3 $INSTALL_DIR/weaver.py'"
fi

echo ""
echo "═══════════════════════════════════════"
echo "Installed. Run:  weaver install"
echo "═══════════════════════════════════════"
python3 weaver.py install
