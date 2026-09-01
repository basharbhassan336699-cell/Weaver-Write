#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# tools/install_searxng_termux.sh
# يثبّت خادم SearXNG محلياً على Termux ويضبطه على 127.0.0.1:8888 مع تفعيل JSON،
# ثم يربطه بـ Weaver Write تلقائياً (يكتب WEAVER_SEARXNG_URL في config/.env).
#
# ملاحظة صريحة: SearXNG ثقيل، وبعض مكتباته (lxml…) تُبنى من مصدر وقد تفشل مع
# إصدارات بايثون الحديثة جداً. السكربت يوقف عند أول فشل ويشرح السبب، ولا يكسر
# نظامك — Weaver يبقى يعمل عبر المحرّك المتعدّد (DuckDuckGo + Bing) بدونه.
#
# التشغيل:   bash tools/install_searxng_termux.sh
# =============================================================================
set -e

SXNG_DIR="$HOME/searxng"
VENV="$HOME/searxng-venv"
SETTINGS_DIR="$HOME/.config/searxng"
SETTINGS="$SETTINGS_DIR/settings.yml"
PORT=8888

say(){ printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn(){ printf '\033[1;33m[!] %s\033[0m\n' "$1"; }
die(){ printf '\033[1;31m[x] %s\033[0m\n' "$1"; exit 1; }

# مجلد مشروع Weaver (حيث يوجد config/) — من موقع السكربت
PROJ="$(cd "$(dirname "$0")/.." && pwd)"

say "1) تثبيت الحزم الأساسية عبر pkg"
pkg update -y || warn "pkg update لم يكتمل — أكمل على أي حال"
pkg install -y python git libxml2 libxslt libjpeg-turbo pkg-config \
    build-essential rust clang || die "فشل تثبيت الحزم. شغّل: pkg install python git libxml2 libxslt build-essential rust"

say "2) جلب SearXNG"
if [ -d "$SXNG_DIR/.git" ]; then
  git -C "$SXNG_DIR" pull --ff-only || warn "تعذّر التحديث، أُكمل بالنسخة الحالية"
else
  git clone --depth 1 https://github.com/searxng/searxng "$SXNG_DIR" \
    || die "فشل استنساخ SearXNG (تحقّق من الإنترنت/VPN)"
fi

say "3) بيئة بايثون معزولة + المتطلبات"
python -m venv "$VENV" || die "تعذّر إنشاء venv"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip setuptools wheel || warn "ترقية pip لم تكتمل"
export LDFLAGS="-L$PREFIX/lib" CFLAGS="-I$PREFIX/include"
if ! pip install -e "$SXNG_DIR"; then
  warn "فشل بناء بعض مكتبات SearXNG (شائع مع إصدار بايثون الحديث على Termux)."
  warn "لم يُكسر شيء: Weaver يعمل عبر المحرّك المتعدّد (DuckDuckGo + Bing)."
  die  "توقّف التثبيت عند بناء المتطلبات."
fi

say "4) إعدادات تفعّل JSON وتربط المنفذ $PORT"
mkdir -p "$SETTINGS_DIR"
SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')"
cat > "$SETTINGS" <<YAML
# إعداد SearXNG محلي لـ Weaver Write — JSON مفعّل
use_default_settings: true
server:
  secret_key: "$SECRET"
  bind_address: "127.0.0.1"
  port: $PORT
  limiter: false
search:
  formats:
    - html
    - json
YAML
echo "كُتب: $SETTINGS"

say "5) ربطه بـ Weaver (config/.env)"
ENV_FILE="$PROJ/config/.env"
[ -f "$ENV_FILE" ] || { [ -f "$PROJ/config/.env.example" ] && cp "$PROJ/config/.env.example" "$ENV_FILE"; }
if [ -f "$ENV_FILE" ] && grep -q '^WEAVER_SEARXNG_URL=' "$ENV_FILE"; then
  sed -i "s|^WEAVER_SEARXNG_URL=.*|WEAVER_SEARXNG_URL=http://127.0.0.1:$PORT|" "$ENV_FILE"
else
  echo "WEAVER_SEARXNG_URL=http://127.0.0.1:$PORT" >> "$ENV_FILE"
fi
echo "ضُبط WEAVER_SEARXNG_URL=http://127.0.0.1:$PORT"

say "تمّ التثبيت ✅"
cat <<DONE

لتشغيل خادم SearXNG (في جلسة Termux مستقلة، أبقِها مفتوحة):
  source "$VENV/bin/activate"
  SEARXNG_SETTINGS_PATH="$SETTINGS" python -m searx.webapp

ثم تأكّد أنه يعمل:
  python tools/test_search.py "أخبار اليوم"
(القسم ٠ و٢ يجب أن يظهرا ✅ الآن)

تذكير: يحتاج SearXNG إنترنت للوصول لمحرّكاته — فعّل VPN إن كانت شبكتك تحجب.
DONE
