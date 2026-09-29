"""
engines/fonts-core/font_catalog.py — كلُّ خطوطنا باسمها الحقيقيّ، وطلبُ خطٍّ بأيّ اسم
====================================================================================
`fonts.py` يعرف خمسةَ خطوطٍ عربيّةٍ بأسماءٍ كتبناها بأيدينا. وقِيس من الملفّات
نفسِها (جدول name في كلِّ ttf):
  · Kufyan-Arabic-Regular.ttf اسمُه الداخليّ «Kufyan Arabic Regular» — والمستنداتُ
    تكتب «Kufyan Arabic»، فلا يطابقه Word ولا يجده الهاتف.
  · ٥٤ خطّاً لاتينيّاً في latin/ لا يعرفها شيء؛ وأحدُها فارغ (IBMPlexSerif-Regular.ttf،
    ٠ بايت).
فهنا فهرسٌ يُقرأ من الملفّات (الاسمُ كما يراه Word: nameID 1)، وبحثٌ يقبل الاسمَ
بأيّ صيغة — «أميري»، «amiri»، «خط القاهرة عريض» — ويعيد الملفَّ الذي يُضمَّن في
المستند أو يُرسم به. وخطٌّ تجاريٌّ لا نملكه (Arial، Simplified Arabic…) يُكتب
باسمه ويُقال إنّه يظهر حيث يكون مثبَّتاً، مع أقربِ خطٍّ عندنا.

لا يحتاج مكتبةً: قارئُ جدول name هنا (fontTools غيرُ لازم).
"""
from __future__ import annotations

import os
import re
import struct

_DIR = os.path.dirname(os.path.abspath(__file__))
_DIRS = (("ar", os.path.join(_DIR, "arabic")), ("latin", os.path.join(_DIR, "latin")))


def _read_names(path):
    """(nameID1, nameID2, fsType, variable) من ملفّ ttf/otf — أو None إن تلف."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 12:
            return None
        num = struct.unpack(">H", data[4:6])[0]
        tables = {}
        for i in range(num):
            tag, _, off, ln = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
            tables[tag.decode("latin-1")] = (off, ln)
        if "name" not in tables:
            return None
        off, _ = tables["name"]
        _fmt, count, sto = struct.unpack(">HHH", data[off:off + 6])
        names = {}
        for i in range(count):
            pid, eid, lid, nid, ln, so = struct.unpack(
                ">HHHHHH", data[off + 6 + 12 * i: off + 18 + 12 * i])
            if nid not in (1, 2, 16):
                continue
            raw = data[off + sto + so: off + sto + so + ln]
            if pid == 3 or (pid == 0):
                txt = raw.decode("utf-16-be", "ignore")
                prio = 2 if (pid == 3 and lid == 0x409) else 1
            elif pid == 1:
                txt = raw.decode("latin-1", "ignore")
                prio = 0
            else:
                continue
            if nid not in names or prio > names[nid][1]:
                names[nid] = (txt, prio)
        fs = 0
        if "OS/2" in tables:
            o, _ = tables["OS/2"]
            fs = struct.unpack(">H", data[o + 8:o + 10])[0]
        fam = names.get(1, ("", 0))[0].strip()
        if not fam:
            return None
        return fam, names.get(2, ("Regular", 0))[0].strip(), fs, "fvar" in tables
    except Exception:
        return None


_STYLE = {"regular": "regular", "bold": "bold", "italic": "italic",
          "bold italic": "bolditalic", "black": "black"}

_CACHE = {}


def catalog():
    """[{family, script, files{regular,bold,italic,bolditalic,black}, embeddable,
    variable}] — مقروءٌ من الملفّات، مرّةً في كلِّ عمليّة."""
    if "cat" in _CACHE:
        return _CACHE["cat"]
    fams = {}
    for script, d in _DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".ttf", ".otf")):
                continue
            p = os.path.join(d, fn)
            info = _read_names(p)
            if not info:
                continue                      # ملفٌّ تالف أو فارغ
            fam, sub, fs, var = info
            key = fam
            e = fams.setdefault(key, {"family": fam, "script": script, "files": {},
                                      "embeddable": True, "variable": False})
            style = _STYLE.get(sub.lower(), "regular" if sub.lower() in (
                "", "book", "normal", "medium", "light") else sub.lower())
            e["files"].setdefault(style, p)
            e["embeddable"] = e["embeddable"] and not (fs & 0x0002)
            e["variable"] = e["variable"] or var
    for e in fams.values():
        e["files"].setdefault("regular", next(iter(e["files"].values())))
    _CACHE["cat"] = sorted(fams.values(), key=lambda x: (x["script"] != "ar",
                                                         x["family"]))
    return _CACHE["cat"]


# أسماءٌ يكتبها الناس ⟵ الخطُّ عندنا (بالاسم الحقيقيّ في الملفّ).
_ALIASES = {
    "أميري": "Amiri", "اميري": "Amiri", "الأميري": "Amiri", "الاميري": "Amiri",
    "القاهرة": "Cairo", "كايرو": "Cairo", "كاهيرو": "Cairo",
    "تجوال": "Tajawal", "تجول": "Tajawal", "تجوّال": "Tajawal",
    "نوتو": "Noto Naskh Arabic", "نوتو نسخ": "Noto Naskh Arabic",
    "نسخ": "Noto Naskh Arabic", "noto": "Noto Naskh Arabic",
    "noto naskh": "Noto Naskh Arabic", "naskh": "Noto Naskh Arabic",
    "كوفيان": "Kufyan Arabic Regular", "كوفي": "Kufyan Arabic Regular",
    "kufyan": "Kufyan Arabic Regular", "kufyan arabic": "Kufyan Arabic Regular",
}

# خطوطٌ تجاريّةٌ شائعة — لا نملك ملفّاتها: تُكتب باسمها، وأقربُ خطٍّ عندنا للرسم.
_COMMERCIAL = {
    "Simplified Arabic": ("ar", "Amiri", ("العربي المبسط", "سمبلفايد", "المبسط")),
    "Traditional Arabic": ("ar", "Amiri", ("العربي التقليدي", "ترديشنال", "التقليدي")),
    "Sakkal Majalla": ("ar", "Amiri", ("مجلة", "مجلّة", "سكال مجلة", "majalla")),
    "Arabic Typesetting": ("ar", "Amiri", ("التنضيد العربي", "typesetting")),
    "Kufyan Arabic Black": ("ar", "Kufyan Arabic Regular", ("كوفيان بلاك", "كوفيان أسود")),
    "Dubai": ("ar", "Cairo", ("دبي",)),
    "Tahoma": ("ar", "Cairo", ("تاهوما",)),
    "Arial": ("latin", "Cairo", ("اريال", "آريال", "أريال")),
    "Times New Roman": ("latin", "Amiri", ("تايمز", "تايمز نيو رومان", "times")),
    "Calibri": ("latin", "Cairo", ("كاليبري",)),
    "Segoe UI": ("latin", "Cairo", ("سيغو",)),
    "Georgia": ("latin", "Amiri", ("جورجيا",)),
}

_WEIGHT_WORDS = {"black": "black", "heavy": "black", "bold": "bold",
                 "عريض": "bold", "غامق": "bold", "ثقيل": "black", "أسود": "black",
                 "italic": "italic", "مائل": "italic", "regular": "regular",
                 "عادي": "regular"}


def _norm(s):
    s = str(s or "").strip().lower()
    s = re.sub(r"^(خط|الخط|font)\s+", "", s)
    s = re.sub(r"[\s\-_]+", " ", s)
    return s.strip()


def _squash(s):
    return re.sub(r"[\s\-_]", "", str(s or "").lower())


def find_font(query):
    """أيُّ خطٍّ طُلب؟ ⟵ dict:
      {"family": الاسمُ الذي يُكتب في الملفّ، "bundled": bool، "files": {…}،
       "script": "ar"|"latin"، "embeddable": bool، "weight": "regular|bold|black|italic",
       "stand_in": خطٌّ عندنا يقوم مقامه في الرسم (للتجاريّ)، "note": نصٌّ للنموذج}
    أو None إن لم يُطلب شيء."""
    q = _norm(query)
    if not q:
        return None
    # الاسمُ كاملاً أوّلاً: «Tajawal Black» عائلةٌ قائمةٌ بذاتها في ملفّها
    for e in catalog():
        if _squash(e["family"]) == _squash(q):
            return {"family": e["family"], "bundled": True, "files": dict(e["files"]),
                    "script": e["script"], "embeddable": e["embeddable"],
                    "weight": "regular", "stand_in": e["family"],
                    "note": "bundled (exact) — embedded in Word files, used in charts"}
    weight = "regular"
    words = q.split()
    for w in list(words):
        if w in _WEIGHT_WORDS:
            weight = _WEIGHT_WORDS[w]
            words.remove(w)
    base = " ".join(words) or q
    cat = catalog()
    by_sq = {_squash(e["family"]): e for e in cat}

    def hit(e, how):
        return {"family": e["family"], "bundled": True, "files": dict(e["files"]),
                "script": e["script"], "embeddable": e["embeddable"],
                "weight": weight, "stand_in": e["family"],
                "note": "bundled (%s) — embedded in Word files, used in charts" % how}

    # ١ خطٌّ تجاريٌّ باسمه أو بمرادفه (قبل البحث الجزئيّ: «Kufyan Arabic Black»)
    for name, (script, stand, aliases) in _COMMERCIAL.items():
        if _squash(base) == _squash(name) or base in [_norm(a) for a in aliases] \
                or (_squash(q) == _squash(name)):
            if name == "Kufyan Arabic Black":
                weight = "black"
            st = next((e for e in cat if e["family"] == stand), None)
            return {"family": name, "bundled": False, "files": {}, "script": script,
                    "embeddable": False, "weight": weight,
                    "stand_in": st["family"] if st else None,
                    "note": ("not bundled — written as '%s'; shows only where it is "
                             "installed (Office on a PC usually has it). Charts use "
                             "'%s'." % (name, st["family"] if st else "default"))}
    # ٢ مرادفٌ عربيٌّ أو شائع
    for a, fam in _ALIASES.items():
        if base == _norm(a):
            e = by_sq.get(_squash(fam))
            if e:
                return hit(e, "alias")
    # ٣ الاسمُ الحقيقيّ، أو بلا مسافات
    e = by_sq.get(_squash(base))
    if e:
        return hit(e, "exact")
    # ٤ جزئيّ: «plex serif» ⟵ IBM Plex Serif · «kufyan» ⟵ Kufyan Arabic Regular
    cands = [e for e in cat if _squash(base) in _squash(e["family"])]
    if len(cands) >= 1:
        cands.sort(key=lambda e: len(e["family"]))
        return hit(cands[0], "partial")
    return {"family": str(query).strip(), "bundled": False, "files": {},
            "script": "ar" if re.search(r"[؀-ۿ]", str(query)) else "latin",
            "embeddable": False, "weight": weight, "stand_in": None,
            "note": "unknown font — written by name as asked; not bundled here. "
                    "Bundled choices: " + ", ".join(e["family"] for e in cat
                                                     if e["script"] == "ar")}


def file_for(entry, weight=None):
    """ملفُّ الخطّ للوزن المطلوب (أو أقربه) — أو None."""
    if not entry or not entry.get("files"):
        return None
    f = entry["files"]
    w = weight or entry.get("weight") or "regular"
    order = {"black": ("black", "bold", "regular"), "bold": ("bold", "regular"),
             "italic": ("italic", "regular"),
             "bolditalic": ("bolditalic", "bold", "italic", "regular")}.get(
        w, ("regular",))
    for k in order:
        if f.get(k):
            return f[k]
    return f.get("regular")


def list_text():
    """نصٌّ مختصرٌ للنموذج: ما عندنا، وما يُكتب باسمه فقط."""
    out = ["ARABIC (bundled, embedded in Word, used in charts):"]
    for e in catalog():
        if e["script"] == "ar":
            out.append("  %s  [%s]%s" % (e["family"], ", ".join(sorted(e["files"])),
                                         "" if e["embeddable"] else " (no embed)"))
    out.append("LATIN (bundled):")
    lat = [e["family"] for e in catalog() if e["script"] == "latin"]
    for i in range(0, len(lat), 4):
        out.append("  " + " · ".join(lat[i:i + 4]))
    out.append("BY NAME ONLY (not bundled; shows where installed): " +
               ", ".join(_COMMERCIAL))
    out.append("Arabic names work too: أميري · القاهرة · تجوال · نوتو نسخ · كوفيان")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        import json
        print(json.dumps(find_font(" ".join(sys.argv[1:])), ensure_ascii=False,
                         indent=1))
    else:
        print(list_text())
