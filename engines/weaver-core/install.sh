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
# بوّابةُ الإصدار — وهي حقيقيّةٌ لا تحذير. مقيسةٌ بالتجربة: على node 22
# يعمل `--version` وحده (مسارٌ سريعٌ قبل الاستيراد)، ثمّ يرفض `preinstall`
# التركيبَ برمز خروج 1، وترفض كلُّ الأوامر الحقيقية بعده:
#   "node:sqlite truncates TEXT at embedded NUL (nodejs/node#61954);
#    use 24.16+/26.1+"
# أي أنّ المحرّك يستعمل قاعدةَ بيانات node المدمجة، و22 يقصُّ النصوص عند
# أوّل بايتٍ صفريّ — فالبيانات تفسد صامتةً. ولذلك البوّابةُ مغلقة.
NODE_V="$(node -p 'process.versions.node')"
NODE_OK="$(node -p 'const [a,b]=process.versions.node.split(".").map(Number); (a===24&&b>=16)||(a>24&&!(a===25))?1:0' 2>/dev/null || echo 0)"
echo "  node v${NODE_V}"
if [ "$NODE_OK" != "1" ]; then
  echo
  echo "  ✗ المحرّك يلزمه node 24.16 فأحدث (أو 26.1+)."
  echo "    والسبب ليس شكلياً: هو يستعمل قاعدةَ بيانات node المدمجة،"
  echo "    وnode 22 يقصُّ النصوصَ عند أوّل بايتٍ صفريّ فتفسد البيانات صامتةً."
  echo
  echo "    على تيرمكس:   pkg install nodejs        # لا nodejs-lts (وهو 22)"
  echo "    ثمّ تحقّق:     node --version"
  echo
  exit 1
fi

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

# `--legacy-peer-deps` ليس تزيّناً: بدونه ينهار npm نفسُه في هذه الحزمة
# بخطأٍ داخليّ في محلِّل الأقران — مقيسٌ لا مُخمَّن:
#   TypeError: Cannot read properties of null (reading 'edgesOut')
#     at #loadPeerSet (@npmcli/arborist/lib/arborist/build-ideal-tree.js:1289)
# فيتوقّف التركيبُ من أوّله. وهذا العَلَم يتخطّى ذلك المسار فيكتمل.
echo "  ⚙ الاعتماديات (٣٢٠ حزمة، قد تطول)…"
( cd "$DEST" && npm install --omit=dev --legacy-peer-deps --no-audit --no-fund ) \
  || { echo "  ⚠ لم تكتمل الاعتماديات — أعِد المحاولة، أو أرسل الخطأ"; }

echo
echo "── تمّ ──"
"$DEST/openclaw.mjs" --version 2>/dev/null || node "$DEST/openclaw.mjs" --version || true
echo
echo "  التشغيل:  python3 -m pipeline.weaver_core --version"
echo "            node $DEST/openclaw.mjs --help"
