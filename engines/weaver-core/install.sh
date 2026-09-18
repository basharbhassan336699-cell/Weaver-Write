#!/data/data/com.termux/files/usr/bin/bash
# تركيبُ محرّك Weaver Write (مبنيٌّ على openclaw، رخصة MIT).
#
# لماذا جلبٌ وإعادةُ تسميةٍ بدل نسخِ الحزمة في المستودع؟ لأنها ٦٧ ميغابايت
# و٩٢٩٢ ملفاً — وضعُها في git يُثقل المستودعَ على كلّ استنساخ. وهذا السكربت
# يُعيد إنتاجها بالضبط في أيّ وقت، ويُثبّت الإصدار فلا يتغيّر تحتك.
#
#   bash engines/weaver-core/install.sh            # الإصدارُ المثبَّت
#   bash engines/weaver-core/install.sh 2026.9.4   # إصدارٌ بعينه
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-2026.9.4}"
DEST="$HERE/runtime"

echo "── محرّك Weaver Write ${VERSION} ──"

command -v node >/dev/null 2>&1 || { echo "✗ node غير مثبّت.  pkg install nodejs"; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "✗ npm غير مثبّت.   pkg install nodejs"; exit 1; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
echo "  node v$(node -p 'process.versions.node')"
[ "$NODE_MAJOR" -lt 22 ] && echo "  ⚠ يُنصح بـnode 22 فأحدث" || true

if [ -d "$DEST" ]; then
  echo "  ✓ مركَّبٌ مسبقاً: $DEST"
  echo "    (احذفه لإعادة التركيب: rm -rf $DEST)"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "  ↓ الجلب…"
( cd "$TMP" && npm pack "openclaw@${VERSION}" >/dev/null 2>&1 ) \
  || { echo "✗ تعذّر الجلب من npm"; exit 1; }
TGZ="$(ls "$TMP"/*.tgz 2>/dev/null | head -1)"
[ -n "$TGZ" ] || { echo "✗ لم يُعَد أرشيف"; exit 1; }

echo "  ⇲ الفكّ…"
mkdir -p "$TMP/x" && tar xzf "$TGZ" -C "$TMP/x"
SRC="$TMP/x/package"
[ -d "$SRC" ] || { echo "✗ بنيةُ أرشيفٍ غيرُ متوقّعة"; exit 1; }

echo "  ✎ إعادةُ التسمية…"
python3 "$HERE/rebrand.py" "$SRC" || { echo "✗ تعذّرت إعادةُ التسمية"; exit 1; }

echo "  ⇒ النقل…"
mkdir -p "$(dirname "$DEST")" && mv "$SRC" "$DEST"

echo "  ⚙ الاعتماديات (قد تطول)…"
( cd "$DEST" && npm install --omit=dev --no-audit --no-fund ) \
  || echo "  ⚠ لم تكتمل الاعتمادياتُ كلُّها — بعضُ الميزات قد لا تعمل"

echo
echo "── تمّ ──"
"$DEST/openclaw.mjs" --version 2>/dev/null || node "$DEST/openclaw.mjs" --version || true
echo
echo "  التشغيل:  python3 -m pipeline.weaver_core --version"
echo "            node $DEST/openclaw.mjs --help"
