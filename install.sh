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
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo "Cloning Weaver Write..."
    git clone "$REPO" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# 4. python deps
echo "Installing Python libraries..."
if [ "$PLATFORM" = "termux" ]; then
    # NOTE: on Termux, `pip install --upgrade pip` is forbidden — it breaks the
    # python-pip package. Ensure pip via pkg, then install requirements directly.
    pkg install -y python-pip 2>/dev/null || true
    pip install -r requirements.txt
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
chmod +x weaver.py
ln -sf "$INSTALL_DIR/weaver.py" "$PREFIX/bin/weaver" 2>/dev/null || \
    sudo ln -sf "$INSTALL_DIR/weaver.py" /usr/local/bin/weaver 2>/dev/null || \
    echo "Add to PATH manually: alias weaver='python3 $INSTALL_DIR/weaver.py'"

echo ""
echo "═══════════════════════════════════════"
echo "Installed. Run:  weaver install"
echo "═══════════════════════════════════════"
python3 weaver.py install
