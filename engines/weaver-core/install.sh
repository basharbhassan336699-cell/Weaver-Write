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
# ── أيُّ إصدارِ node؟ لا بوّابةٌ تُغلق كلَّ شيء ──────────────────────────
#
# المحرّكُ يشترط ">=24.16.0 <25 || >=26.1.0"، وهو شرطٌ حقيقيٌّ لا شكليّ:
# يستعمل قاعدةَ بيانات node المدمجة، ودون 24.16 يقصُّ النصَّ عند أوّل بايتٍ
# صفريّ (nodejs/node#61954) فتفسد البيانات صامتةً. فلا يُتجاوَز بصمت.
#
# لكنّ إغلاقَ النظام كلِّه بسببه خطأ: المسارُ البايثونيُّ يعمل بلا node
# أصلاً. فالسكربتُ يبحث في كلّ ما على الجهاز — لا المسارِ الافتراضيِّ وحده،
# فقد يكون ثمّة إصدارٌ صالحٌ تحت nvm أو تيرمكس — فإن وجده ركّب، وإلّا قال
# الناقصَ بدقّةٍ وخرج بنجاحٍ لا بفشل: النظامُ يعمل، والمحرّكُ إضافةٌ مؤجَّلة.
# المقارنةُ في الصَدَفة لا داخل node: أمتنُ (لا تعتمد على تنفيذ تعبيرٍ في
# المُرشَّح) وتطابق حرفياً ما يفعله `node_ok` في pipeline/weaver_core.py،
# فلا يقول السكربتُ شيئاً ويقول الجسرُ غيرَه.
node_ok() {                     # $1 = "26.4.0"
  a="${1%%.*}"; r="${1#*.}"; b="${r%%.*}"
  case "$a" in ''|*[!0-9]*) return 1;; esac
  case "$b" in ''|*[!0-9]*) b=0;; esac
  [ "$a" -eq 24 ] && [ "$b" -ge 16 ] && return 0
  [ "$a" -eq 26 ] && [ "$b" -ge 1 ]  && return 0
  [ "$a" -gt 26 ] && return 0
  return 1
}
PICKED=""
SEEN=""
echo "  البحثُ عن node صالح…"
for C in "$WEAVER_NODE" "$(command -v node 2>/dev/null)" \
         "$PREFIX/bin/node" "/data/data/com.termux/files/usr/bin/node" \
         "/usr/local/bin/node" "/usr/bin/node" \
         "$HOME"/.nvm/versions/node/*/bin/node /opt/node*/bin/node; do
  [ -x "$C" ] || continue
  # المُرشَّحون يتكرّرون: `command -v node` و`$PREFIX/bin/node` و مسارُ تيرمكس
  # الصريح كلُّها ملفٌّ واحد. فيُحلّ المسارُ الحقيقيُّ ويُطرح المكرَّر — وإلّا
  # طُبع الإصدارُ نفسُه ثلاثَ مرّاتٍ فبدا كأنّ على الجهاز ثلاثةَ أنودات.
  R="$(readlink -f "$C" 2>/dev/null || echo "$C")"
  case " $SEEN " in *" $R "*) continue;; esac
  SEEN="$SEEN $R"
  V="$("$C" -p 'process.versions.node' 2>/dev/null)" || continue
  [ -n "$V" ] || continue
  if node_ok "$V"; then
    echo "    ✓ v$V   $C"
    [ -z "$PICKED" ] && PICKED="$C"
  else
    echo "    · v$V   $C   (دون الشرط)"
  fi
done

if [ -z "$PICKED" ]; then
  echo
  echo "  لا إصدارَ يفي بشرط المحرّك (>=24.16 <25 || >=26.1)."
  echo "  والشرطُ حقيقيّ: دون 24.16 يقصُّ node النصوصَ في قاعدة بياناته"
  echo "  المدمجة فتفسد البيانات صامتةً — فلا نتجاوزه."
  echo
  echo "    الترقية:  pkg install nodejs          # لا nodejs-lts (وهو 22)"
  echo "    أو:       export WEAVER_NODE=/مسار/node/الصالح"
  echo
  echo "  ✔ ونظامُك يعمل الآن بلا محرّك — المسارُ البايثونيّ:"
  echo "      python3 -m pipeline.agent \"أيّ سؤال\""
  echo "      python3 -m pipeline.weaver_core --doctor"
  exit 0          # ليس فشلاً: النظامُ يعمل، والمحرّكُ مؤجَّل
fi
NODE="$PICKED"
echo "  المختار: $NODE  (v$("$NODE" -p 'process.versions.node'))"

if [ -d "$DEST" ]; then
  echo "  ✓ مركَّبٌ مسبقاً: $DEST"
  echo "    (احذفه لإعادة التركيب: rm -rf $DEST)"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# `npm pack` لا يطبع تقدّماً، فتبدو الشاشةُ ساكنةً دقائقَ على بيانات الجوّال
# والمستخدمُ يظنُّ أنّه تعلّق. فيُقال الحجمُ والمتوقَّع قبل أن يبدأ.
echo "  ↓ الجلب… (~67 ميغابايت — قد يطول، ولا يَظهر تقدّم. لا تُغلق)"
( cd "$TMP" && npm pack "openclaw@${VERSION}" >/dev/null 2>&1 ) \
  || { echo "✗ تعذّر الجلب من npm"; exit 1; }
TGZ="$(ls "$TMP"/*.tgz 2>/dev/null | head -1)"
[ -n "$TGZ" ] || { echo "✗ لم يُعَد أرشيف"; exit 1; }

echo "  ⇲ الفكّ… (9292 ملفاً)"
mkdir -p "$TMP/x" && tar xzf "$TGZ" -C "$TMP/x"
SRC="$TMP/x/package"
[ -d "$SRC" ] || { echo "✗ بنيةُ أرشيفٍ غيرُ متوقّعة"; exit 1; }

echo "  ✎ إعادةُ التسمية… (~15600 موضعاً)"
python3 "$HERE/rebrand.py" "$SRC" || { echo "✗ تعذّرت إعادةُ التسمية"; exit 1; }

# رقعةُ نقلٍ واحدة: `/tmp` المكتوبُ حرفياً في موضعين ⟶ `os.tmpdir()`.
# على أندرويد `/tmp` للقراءة فقط، فتفشل أقفالُ قاعدة الحالة بـEACCES.
# وهي تتحقّق من السطر بنصّه قبل أن تُعدّل، وتتوقّف إن تغيّر الإصدار.
echo "  ⛭ رقعةُ النقل…"
python3 "$HERE/patch_portability.py" "$SRC" \
  || echo "    ⚠ لم تُطبَّق كاملةً — المحرّك يعمل، وقد تفشل أوامرُ الحالة"

echo "  ⇒ النقل…"
mkdir -p "$(dirname "$DEST")" && mv "$SRC" "$DEST"

# `--legacy-peer-deps` ليس تزيّناً: بدونه ينهار npm نفسُه في هذه الحزمة
# بخطأٍ داخليّ في محلِّل الأقران — مقيسٌ لا مُخمَّن:
#   TypeError: Cannot read properties of null (reading 'edgesOut')
#     at #loadPeerSet (@npmcli/arborist/lib/arborist/build-ideal-tree.js:1289)
# فيتوقّف التركيبُ من أوّله. وهذا العَلَم يتخطّى ذلك المسار فيكتمل.
echo "  ⚙ الاعتماديات (٣٢٠ حزمة، قد تطول)…"
( cd "$DEST" && PATH="$(dirname "$NODE"):$PATH" npm install --omit=dev --legacy-peer-deps --no-audit --no-fund ) \
  || { echo "  ⚠ لم تكتمل الاعتماديات — أعِد المحاولة، أو أرسل الخطأ"; }

# ── بحثُ الويب: بآليّة أوبن كلاو نفسِها، بلا حرفٍ من عندنا ────────────────
#
# أداتا `web_search` و`web_fetch` في المحرّك أصلاً. لكنّ المزوّدَ لا يأتي
# مُرفَقاً: أوبن كلاو يجعله إضافةً رسميّةً تُركَّب، ثمّ يختار تلقائياً بترتيبٍ
# مُعلَنٍ في كتالوجه (autoDetectOrder):
#
#     brave 10 · kimi 40 · perplexity 50 · firecrawl 60 · exa 65
#     tavily 70 · parallel 75 · duckduckgo 100 · searxng 200
#
# فنُركّب اثنتين من كتالوجه هو، بأمره هو:
#   • perplexity (٥٠) — يقرأ OPENROUTER_API_KEY، وهو مفتاحُ النظام أصلاً
#   • duckduckgo (١٠٠) — بلا مفتاح، فيبقى البحثُ عاملاً على كلّ حال
#
# ولا نلمس قواعدَ النظام الأكاديمية: هذه أدواتُ المحرّك وحده.
_OC () { OPENCLAW_STATE_DIR="$STATE_DIR" OPENCLAW_PROFILE=weaver \
         "$NODE" "$DEST/openclaw.mjs" "$@" >/dev/null 2>&1; }
STATE_DIR="${WEAVER_STATE_DIR:-$HOME/.weaver-write/state}"
ROOT="$(cd "$HERE/../.." && pwd)"
# ── نموذجُك ومفتاحُك في إعداد المحرّك ─────────────────────────────────────
#
# بلا هذا يسقط المحرّكُ إلى افتراضيّه `openai/gpt-5.6-sol`، ولا مفتاحَ له،
# فتفشل كلُّ نوبةٍ بـ«No route-compatible authentication source».
# والشكلُ موثَّقٌ في docs/providers/openrouter.md:
#     { env: { vars: { OPENROUTER_API_KEY: … } },
#       agents: { defaults: { model: { primary: "openrouter/…" } } } }
# ── تهيئةُ أوبن كلاو الكاملة ──────────────────────────────────────────────
#
# «openclaw onboard — Guided setup for auth, models, Gateway, workspace,
#  channels, and skills» — أمرُه هو، يفعل في نداءٍ واحدٍ ما كنّا نبنيه
# قطعةً قطعة: ملفَّ اعتمادٍ (auth.profiles)، ووكيلاً باسمٍ ومساحةِ عمل،
# وتفعيلَ إضافةِ المزوّد، وإعدادَ البوّابة، وملفَّ الأدوات، والمهارات.
# ويثبّت الجسرُ بعده نموذجَك بعينه فوق `openrouter/auto`.
echo "  ⚙ تهيئةُ المحرّك بمفتاحك (auth · models · gateway · workspace)…"
( cd "$ROOT" && WEAVER_NODE="$NODE" python3 -m pipeline.weaver_core --onboard 2>&1 \
  | sed 's/^/    /' ) || echo "    ⚠ تعذّرت التهيئة"

echo "  ⌕ بحثُ الويب (إضافاتُ أوبن كلاو الرسميّة)…"
for _P in duckduckgo perplexity; do
  if _OC plugins install "@openclaw/${_P}-plugin" --accept-capabilities; then
    echo "    ✓ ${_P}"
  else
    echo "    ⚠ ${_P} — لم تُركَّب (شبكة؟). البحثُ يعمل بما تبقّى"
  fi
done
# والتفعيلُ وحده لا يكفي: المحرّكُ يختار المزوّدَ بمفتاحه، وduckduckgo بلا
# مفتاحٍ فلا يُكتشَف تلقائياً أبداً. فيُترك الإتمامُ للجسر: يفحص أيُّ مزوّدٍ
# حُلّ، ويُعيّن duckduckgo صراحةً إن لم يُحَلّ شيء.
( cd "$ROOT" && WEAVER_NODE="$NODE" python3 -m pipeline.weaver_core --web-search 2>&1 \
  | sed 's/^/    /' ) || echo "    ⚠ تعذّر إعدادُ بحثِ الويب"

# ── واختيارُك أنت: معالجُ أوبن كلاو نفسُه ──────────────────────────────────
#
#   docs/cli/configure.md:74
#   «openclaw configure --section web picks a web-search provider and
#    configures its credentials.»
#
# يعرض المزوّدين — المجّانيَّ والمدفوع — ويأخذ المفتاحَ إن لزم. ونحن لا نبني
# قائمةً من عندنا: نناديه هو، فتبقى المعماريّةُ معماريّتَه، وتنمو قائمتُه
# بترقيته بلا أن نلمس شيئاً.
#
# ويشترط طرفيّةً تفاعليّة (docs/cli/configure.md:40)، فلا يُعرض إلّا إن
# وُجدت — ومَن تخطّاها يجدها أمراً في أيّ وقت.
if [ -t 0 ] && [ -t 1 ]; then
  echo
  printf "  ⌕ تختار محرّكَ البحث الآن؟ (المجّانيّ والمدفوع) [y/N] "
  read -r _ans </dev/tty || _ans=""
  case "$_ans" in
    [yY]*)
      ( cd "$ROOT" && WEAVER_NODE="$NODE" \
        python3 -m pipeline.weaver_core --web-search choose ) || true
      ;;
    *)
      echo "    تخطّيت. ولاختياره لاحقاً في أيّ وقت:"
      echo "      python3 -m pipeline.weaver_core --web-search choose"
      ;;
  esac
else
  echo "    ولاختيار محرّك البحث بنفسك:"
  echo "      python3 -m pipeline.weaver_core --web-search choose"
fi

echo
echo "── تمّ ──"
"$NODE" "$DEST/openclaw.mjs" --version || true
echo
echo "  التشغيل:  python3 -m pipeline.weaver_core --version"
echo "            node $DEST/openclaw.mjs --help"
