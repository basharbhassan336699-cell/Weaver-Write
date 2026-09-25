#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""قارئُ PDF صفحةً صفحة — برقم كلِّ صفحة، عربيّاً وإنجليزيّاً، من رابطٍ أو ملفّ.

يعطي النموذجَ نصَّ الملفّ وعلى رأس كلِّ صفحةٍ رقمُها:

    === ص. 12 ===
    …نصُّ الصفحة الثانية عشرة…

فيستشهد برقمٍ قرأه لا برقمٍ خمّنه.

**من الإنترنت مباشرةً:** يُعطى رابطاً فينزّله بنفسه إلى ملفٍّ مؤقّت ويقرؤه
ثمّ يحذفه — لا ينزّل المستخدمُ شيئاً. وإن كان الرابطُ صفحةَ مقالٍ لا ملفّاً
فيتبع `citation_pdf_url` (الوسمُ القياسيّ الذي تضعه المجلّاتُ وarXiv لملفّ
المقال)، وarxiv.org/abs/… ⟵ arxiv.org/pdf/…. ويقرأ الملفّاتِ المحليّة أيضاً
(ما أرسله المستخدمُ في المحادثة).

**ترتيبُ القراءة — مقيسٌ على هاتف المستخدم وعلى ملفّاتٍ عربيّةٍ حقيقيّة:**

  ١ pdftotext  (poppler) — يُخرج العربيّةَ بترتيبها المنطقيّ الصحيح.
  ٢ pypdf      — إن فشل الأوّل. (قِيس: يقلب ترتيبَ الكلمات العربيّة أحياناً،
                 فهو ثانٍ لا أوّل.)
  ٣ OCR        — tesseract (ara+eng) للصفحة التي فشل فيها الاثنان وحدها:
                 ملفٌّ ممسوح، أو ملفٌّ عربيٌّ خريطةُ حروفه تالفة (شائع: يخرج
                 رموزاً لا كلمات). وتُوسَم الصفحةُ [OCR] لأنّ OCR قد يخطئ في
                 الأرقام (قِيس: «45%» قُرئت «9645») — فيُتحقَّق منها.

وتُنظَّف المُخرَجات: أشكالُ العرض العربيّة (ﺍﻟﻌﺮﺑﻴﺔ) ⟵ حروفٌ عاديّة، وتُحذف
علاماتُ الاتّجاه الخفيّة. ولا يُغيَّر سوى ذلك.

    python3 pipeline/pdf_pages.py <رابط|ملفّ> [--pages 3-7,10] [--out ملفّ]
                                  [--json] [--ocr auto|off|force]
                                  [--find "اقتباس"]

    رموزُ الخروج: 0 كلُّ الصفحات قُرئت · 3 قُرئ بعضُها · 2 تعذّرت القراءة
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

MAX_BYTES = 60 * 1024 * 1024          # ملفٌّ أكبرُ من هذا لا يُنزَّل
MAX_PAGES = 80                        # ما يُقرأ افتراضياً بلا --pages
MAX_OCR_PAGES = 30                    # OCR بطيءٌ على الهاتف: حدٌّ معلَن
UA = ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Mobile Safari/537.36 WeaverWrite")

_BIDI = re.compile("[‎‏‪-‮⁦-⁩﻿]")
_AR = re.compile("[؀-ۿݐ-ݿࢠ-ࣿ]")
_AR_TOKEN = re.compile("[؀-ۿݐ-ݿࢠ-ࣿ]+")


# ── التنظيف ─────────────────────────────────────────────────────────────
def clean(text):
    """أشكالُ العرض العربيّة ⟵ الحروف، وحذفُ علامات الاتّجاه. لا شيءَ غيرهما."""
    t = _BIDI.sub("", str(text or ""))
    return "".join(unicodedata.normalize("NFKC", c)
                   if ("ﭐ" <= c <= "﷿" or "ﹰ" <= c <= "﻾")
                   else c for c in t)


def _allowed_letter(c):
    o = ord(c)
    return (_AR.match(c) is not None or o < 0x250          # لاتينيّ + ممتدّ
            or 0x370 <= o < 0x400                          # يونانيّ (رموزٌ علميّة)
            or 0x1e00 <= o < 0x1f00)                       # لاتينيٌّ ممتدٌّ إضافيّ


def quality(text):
    """(صالح؟، السبب). يحكم على **شكل** النصّ لا معناه:

    · حروفٌ قليلة جداً              ⟵ صفحةٌ فارغة أو صورة
    · حروفٌ من غير العربيّة واللاتينيّة ⟵ خريطةُ حروفٍ تالفة (رموزٌ لا كلمات)
    · حروفٌ عربيّةٌ مفكَّكة           ⟵ «ا ل ك ت ا ب» بدل «الكتاب»
    · كلماتٌ تبدأ بـة أو ى            ⟵ حروفٌ مقلوبة (ترتيبٌ بصريّ)"""
    t = clean(text)
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 20:
        return False, "فارغة أو صورة"
    bad = sum(1 for c in t if c == "�" or "" <= c <= ""
              or (c.isalpha() and not _allowed_letter(c)))
    if bad / max(1, len(letters)) > 0.12:
        return False, "رموزٌ لا كلمات (خريطةُ حروفٍ تالفة)"
    toks = _AR_TOKEN.findall(t)
    single = sum(1 for w in toks if len(w) == 1 and w not in "وبلكف")
    # كثيرةٌ ونسبةُ المفكَّك فيها عالية — أو قليلةٌ وأغلبُها حرفٌ واحد
    # (قِيس: صفحةٌ إنجليزيّةٌ سليمةٌ وسطها عربيٌّ تالف «ا آ ا» كانت تمرّ).
    if (len(toks) >= 8 and single / len(toks) > 0.35) or (
            len(toks) >= 3 and single / len(toks) > 0.5):
        return False, "حروفٌ عربيّةٌ مفكَّكة"
    if len(toks) >= 8:
        rev = sum(1 for w in toks if w[0] in "ةى")
        if rev / len(toks) > 0.08:
            return False, "حروفٌ عربيّةٌ مقلوبة"
    return True, ""


# ── المصدر: رابطٌ أو ملفّ ───────────────────────────────────────────────
def _to_uri(url):
    try:
        from pipeline.plagiarism import to_uri
        return to_uri(url)
    except Exception:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            from pipeline.plagiarism import to_uri
            return to_uri(url)
        except Exception:
            return url


def _arxiv_pdf(url):
    m = re.match(r"https?://(?:www\.)?arxiv\.org/abs/([^?#]+)", url or "")
    return ("https://arxiv.org/pdf/" + m.group(1)) if m else url


def _pdf_link_in_html(html, base):
    """`<meta name="citation_pdf_url" content="…">` — وسمُ ملفّ المقال القياسيّ."""
    from urllib.parse import urljoin
    for m in re.finditer(r"<meta\b[^>]*>", html or "", re.I):
        tag = m.group(0)
        if re.search(r"""name\s*=\s*["']citation_pdf_url["']""", tag, re.I):
            c = re.search(r"""content\s*=\s*["']([^"']+)["']""", tag, re.I)
            if c:
                return urljoin(base, c.group(1).strip())
    return ""


def download(url, timeout=90, _hop=0):
    """(مسارٌ مؤقّت، رابطٌ نهائيّ، خطأ). يتبع صفحةَ المقال إلى ملفّها مرّةً واحدة."""
    import urllib.request
    import urllib.error
    url = _arxiv_pdf(url)
    try:
        req = urllib.request.Request(_to_uri(url), headers={
            "User-Agent": UA, "Accept": "application/pdf,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final = r.geturl()
            head = r.read(2048)
            if b"%PDF" not in head[:1024]:
                ctype = (r.headers.get("Content-Type") or "").lower()
                if _hop == 0 and ("html" in ctype or b"<html" in head.lower()
                                  or b"<!doctype" in head.lower()):
                    rest = r.read(2 * 1024 * 1024)
                    html = (head + rest).decode("utf-8", "replace")
                    nxt = _pdf_link_in_html(html, final)
                    if nxt:
                        return download(nxt, timeout, _hop + 1)
                    return None, final, ("الرابطُ صفحةُ ويب لا ملفّ PDF، ولا رابطَ "
                                         "PDF فيها (citation_pdf_url)")
                return None, final, "ليس ملفَّ PDF (%s)" % (ctype or "نوعٌ مجهول")
            fd, path = tempfile.mkstemp(prefix="weaver_pdf_", suffix=".pdf")
            size = len(head)
            with os.fdopen(fd, "wb") as fh:
                fh.write(head)
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        fh.close()
                        os.remove(path)
                        return None, final, ("الملفُّ أكبرُ من %d ميغابايت"
                                             % (MAX_BYTES // 1048576))
                    fh.write(chunk)
            return path, final, ""
    except urllib.error.HTTPError as e:
        return None, url, "HTTP %d — الموقعُ رفض التنزيل" % e.code
    except Exception as e:
        return None, url, "%s: %s" % (type(e).__name__, str(e)[:160])


# ── القرّاء ─────────────────────────────────────────────────────────────
def _run(cmd, timeout=180, text=True):
    return subprocess.run(cmd, capture_output=True, text=text, timeout=timeout)


def page_count(path):
    if shutil.which("pdfinfo"):
        try:
            out = _run(["pdfinfo", path], timeout=60).stdout
            m = re.search(r"^Pages:\s+(\d+)", out, re.M)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    try:
        import logging
        logging.getLogger("pypdf").setLevel(logging.CRITICAL)
        import pypdf
        return len(pypdf.PdfReader(path).pages)
    except BaseException:            # pypdf قد يرفع PanicException (من Rust)
        pass
    if shutil.which("pdftotext"):
        try:
            out = _run(["pdftotext", path, "-"], timeout=300).stdout
            return max(1, out.count("\f"))
        except Exception:
            pass
    return 0


def _pdftotext_pages(path, first, last):
    """{رقم: نصّ} بنداءٍ واحد للمدى كلِّه (الصفحاتُ مفصولةٌ بـ\\f)."""
    if not shutil.which("pdftotext"):
        return {}
    try:
        out = _run(["pdftotext", "-f", str(first), "-l", str(last), path, "-"],
                   timeout=300).stdout
    except Exception:
        return {}
    parts = out.split("\f")
    return {first + i: parts[i] for i in range(min(len(parts), last - first + 1))}


def _pypdf_reader(path):
    try:
        import logging
        logging.getLogger("pypdf").setLevel(logging.CRITICAL)   # ضجيجُ الملفّات التالفة
        import pypdf
        return pypdf.PdfReader(path)
    except BaseException:
        return None


def _pypdf_page(reader, n):
    try:
        return reader.pages[n - 1].extract_text() or ""
    except BaseException:
        return ""


def ocr_langs():
    if not shutil.which("tesseract"):
        return ""
    try:
        r = _run(["tesseract", "--list-langs"], timeout=30)
        langs = set((r.stdout + r.stderr).split())
    except Exception:
        return ""
    return "+".join(x for x in ("ara", "eng") if x in langs)


def _ocr_page(path, n, langs):
    if not (langs and shutil.which("pdftoppm")):
        return ""
    tmp = tempfile.mkdtemp(prefix="weaver_ocr_")
    try:
        base = os.path.join(tmp, "p")
        _run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", "300", "-gray",
              "-png", path, base], timeout=240)
        imgs = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        if not imgs:
            return ""
        r = _run(["tesseract", os.path.join(tmp, imgs[0]), "-", "-l", langs],
                 timeout=300)
        return r.stdout or ""
    except Exception:
        return ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def parse_pages(spec, total):
    """«3-7,10» ⟵ [3,4,5,6,7,10] داخل حدود الملفّ."""
    out = []
    for part in str(spec or "").replace("،", ",").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out += list(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.append(int(part))
    return sorted({p for p in out if 1 <= p <= total})


def read_pdf(path, pages=None, ocr="auto", say=None):
    """dict: ok · pages_total · pages[{page, method, text, note}] · warnings."""
    total = page_count(path)
    if not total:
        return {"ok": False, "pages_total": 0, "pages": [],
                "warnings": [], "error": "تعذّر فتحُ الملفّ (ليس PDF سليماً؟)"}
    warnings = []
    want = parse_pages(pages, total) if pages else list(range(1, total + 1))
    if not pages and total > MAX_PAGES:
        want = want[:MAX_PAGES]
        warnings.append("الملفُّ %d صفحة — قُرئت أوّلُ %d؛ للباقي: --pages %d-%d"
                        % (total, MAX_PAGES, MAX_PAGES + 1, total))
    if not want:
        return {"ok": False, "pages_total": total, "pages": [], "warnings": [],
                "error": "لا صفحاتَ في المدى المطلوب (الملفُّ %d صفحة)" % total}
    langs = ocr_langs() if ocr != "off" else ""
    if ocr != "off" and not langs:
        warnings.append("OCR غيرُ متاح (tesseract/pdftoppm) — الصفحاتُ الممسوحة "
                        "تبقى فارغة")
    ptt = _pdftotext_pages(path, want[0], want[-1])
    reader = None
    rows, ocr_used = [], 0
    for n in want:
        text, method, note = "", "", ""
        cands = []
        if ocr != "force":
            t1 = clean(ptt.get(n, ""))
            ok1, why1 = quality(t1)
            cands.append((t1, "pdftotext", ok1, why1))
            if not ok1:
                if reader is None:
                    reader = _pypdf_reader(path) or False
                t2 = clean(_pypdf_page(reader, n)) if reader else ""
                ok2, why2 = quality(t2)
                cands.append((t2, "pypdf", ok2, why2))
        good = next((c for c in cands if c[2]), None)
        if good is None and langs and ocr_used < MAX_OCR_PAGES:
            if say:
                say("… OCR للصفحة %d" % n)
            t3 = clean(_ocr_page(path, n, langs))
            ocr_used += 1
            ok3, why3 = quality(t3)
            cands.append((t3, "ocr", ok3, why3))
            if ok3 or len(t3.strip()) > 0:
                good = (t3, "ocr", ok3, why3)
        elif good is None and langs and ocr_used >= MAX_OCR_PAGES:
            note = "لم تُقرأ بـOCR — بلغ الحدّ (%d صفحة)" % MAX_OCR_PAGES
        if good is None:
            # لا قراءةَ صالحة: الأطولُ مع التنبيه، لا نصٌّ مختلَق.
            best = max(cands, key=lambda c: len(c[0].strip())) if cands else (
                "", "", False, "لا قارئ")
            text, method = best[0], best[1]
            note = note or ("تعذّرت القراءة: " + (best[3] or "فارغة"))
        else:
            text, method = good[0], good[1]
            if not good[2]:
                note = "قراءةٌ ضعيفة: " + good[3]
        if method == "ocr":
            note = (note + " · " if note else "") + \
                "قُرئت بـOCR — تحقّق من الأرقام والاقتباسات"
        rows.append({"page": n, "method": method,
                     "text": text.strip(), "note": note})
    readable = [r for r in rows if r["text"] and not r["note"].startswith(
        "تعذّرت")]
    return {"ok": bool(readable), "pages_total": total, "pages": rows,
            "read": len(readable), "requested": len(rows),
            "warnings": warnings, "error": "" if readable else
            "لم تُقرأ أيُّ صفحة"}


# ── البحثُ عن اقتباسٍ حرفيّ: في أيّ صفحة؟ ────────────────────────────────
def _fold(s):
    s = clean(s)
    s = re.sub("[ً-ٰٟـ]", "", s)           # تشكيلٌ وتطويل
    s = s.translate(str.maketrans("أإآٱىة", "اااايه"))
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


def find(result, quote):
    """أرقامُ الصفحات التي فيها الاقتباسُ حرفياً (بلا اعتبارٍ للتشكيل والمسافات
    وأسطرٍ مكسورة بين صفحتين متتاليتين)."""
    q = _fold(quote)
    if not q:
        return []
    pages = result.get("pages") or []
    hits = [p["page"] for p in pages if q in _fold(p["text"])]
    if hits:
        return hits
    for a, b in zip(pages, pages[1:]):                 # اقتباسٌ عابرٌ لصفحتين
        if b["page"] == a["page"] + 1 and q in _fold(a["text"] + " " + b["text"]):
            hits.append(a["page"])
    return hits


# ── الواجهة ─────────────────────────────────────────────────────────────
def render(result, source=""):
    out = []
    if source:
        out.append("المصدر: " + source)
    out.append("الصفحات: %d في الملفّ · قُرئت %d من %d" % (
        result.get("pages_total", 0), result.get("read", 0),
        result.get("requested", 0)))
    for w in result.get("warnings") or []:
        out.append("⚠ " + w)
    for p in result.get("pages") or []:
        tag = " [OCR]" if p["method"] == "ocr" else ""
        out.append("\n=== ص. %d ===%s" % (p["page"], tag))
        if p["note"]:
            out.append("(%s)" % p["note"])
        out.append(p["text"] or "")
    return "\n".join(out).strip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="قارئُ PDF صفحةً صفحة برقم كلِّ صفحة — من رابطٍ أو ملفّ.")
    ap.add_argument("source", help="رابطُ الملفّ (أو صفحةِ المقال) أو مسارُه")
    ap.add_argument("--pages", help="مثلاً 3-7,10")
    ap.add_argument("--ocr", choices=("auto", "off", "force"), default="auto")
    ap.add_argument("--out", help="اكتب النصَّ في ملفّ بدل طباعته")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--find", help="في أيّ صفحةٍ هذا الاقتباسُ الحرفيّ؟")
    a = ap.parse_args(argv)

    src = a.source.strip()
    tmp = None
    if re.match(r"^https?://", src, re.I):
        print("… تنزيلُ الملفّ", file=sys.stderr)
        tmp, final, err = download(src)
        if not tmp:
            print("✗ " + err, file=sys.stderr)
            return 2
        path, label = tmp, final
    else:
        path = os.path.expanduser(src)
        label = src
        if not os.path.isfile(path):
            print("✗ الملفُّ غيرُ موجود: " + src, file=sys.stderr)
            return 2
    try:
        res = read_pdf(path, a.pages, a.ocr,
                       say=lambda s: print(s, file=sys.stderr))
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
    res["source"] = label
    if not res.get("ok"):
        print("✗ " + (res.get("error") or "تعذّرت القراءة"), file=sys.stderr)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        return 2
    if a.find is not None:
        hits = find(res, a.find)
        res["found_pages"] = hits
        if not a.json:
            print(("✓ الاقتباسُ في ص. " + "، ".join(map(str, hits))) if hits
                  else "✗ الاقتباسُ غيرُ موجودٍ حرفياً في الصفحات المقروءة")
            return 0 if hits else 1
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(render(res, label))
        print("✓ كُتب في %s — %d صفحة مقروءة من %d" % (
            a.out, res["read"], res["requested"]))
    else:
        sys.stdout.write(render(res, label))
    return 0 if res["read"] == res["requested"] else 3


if __name__ == "__main__":
    sys.exit(main())
