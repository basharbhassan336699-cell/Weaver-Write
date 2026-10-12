"""أوّلُ ردٍّ بعد التحديث: لا إقلاعَ للمحرّك إلا حين يتغيّر كودُه، ولا عمليّاتٍ يتيمة.

    python3 tests/test_fast_restart.py

قِيس على هاتف المستخدم: إقلاعُ البوّابة «74.3s» ثمّ ~٢٣ ث تجهيزاً لأوّل نوبة —
وأمرُ التحديث كان يُطفئها في كلِّ مرّة. وقِيس هنا على المحرّك الحقيقيّ:
    SOUL.md ونصُّ المهارة يصلان البوّابةَ الحيّةَ فوراً، وقائمةُ المهارات خلال ثوانٍ
    حيّةٌ وكودُها لم يتغيّر ⟵ «كانت حيّةً سلفاً» (0.0 ث)
    كودُها تغيّر ⟵ تُطفأ وتُقلع على الجديد (9 ث هنا)
    العمليةُ المقيمةُ القديمة بعد قتل الخادم ⟵ ١ يتيمة؛ الجديدة ⟵ ٠
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import weaver_core as W  # noqa: E402

FAILS = []


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        FAILS.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="wv-fr-")
    saved = (W.ENTRY, W.ENGINE_BOOTED, W.gateway_health, W.gateway_stop,
             W.node_bin, W.available)
    try:
        rt = os.path.join(tmp, "runtime")
        os.makedirs(os.path.join(rt, "dist"))
        open(os.path.join(rt, "package.json"), "w").write('{"version": "9.9.9"}')
        open(os.path.join(rt, "openclaw.mjs"), "w").write("//")
        open(os.path.join(rt, "dist", "a.mjs"), "w").write("//")
        W.ENTRY = os.path.join(rt, "openclaw.mjs")
        W.ENGINE_BOOTED = os.path.join(tmp, "engine.booted")
        fp = W.engine_code_fp(fresh=True)
        check("البصمة: الإصدار + أحدثُ تعديل", fp.startswith("9.9.9@"))
        os.utime(os.path.join(rt, "dist", "a.mjs"), (2e9, 2e9))
        check("البصمةُ تُحسب مرّةً لكلِّ عمليّة (لا مسحَ في كلِّ رسالة)",
              W.engine_code_fp() == fp)
        fp2 = W.engine_code_fp(fresh=True)
        check("ملفٌّ في المحرّك تغيّر ⟵ بصمةٌ أخرى", fp2 != fp)

        stops = []
        W.gateway_health = lambda *a, **k: True
        W.gateway_stop = lambda: stops.append(1) or (True, "")
        W.node_bin = lambda: None          # لا إقلاعَ حقيقيٌّ في الاختبار
        W.available = lambda: False

        r = W.gateway_start()
        check("حيّةٌ ولا بصمةَ محفوظة ⟵ تبقى حيّة وتُحفظ البصمة",
              r[0] and not stops and open(W.ENGINE_BOOTED).read() == fp2)
        r = W.gateway_start()
        check("حيّةٌ وكودُها لم يتغيّر ⟵ لا إطفاء", r[0] and not stops)
        os.utime(os.path.join(rt, "dist", "a.mjs"), (2.1e9, 2.1e9))
        W.engine_code_fp(fresh=True)
        W.gateway_start()
        check("كودُ المحرّك تغيّر ⟵ تُطفأ لتُقلع على الجديد", stops == [1])
        W.ENTRY = os.path.join(tmp, "missing", "openclaw.mjs")
        W.engine_code_fp(fresh=True)
        stops.clear()
        W.gateway_start()
        check("لا محرّكَ يُقرأ ⟵ لا بصمة ⟵ لا إطفاء", not stops)
    finally:
        (W.ENTRY, W.ENGINE_BOOTED, W.gateway_health, W.gateway_stop,
         W.node_bin, W.available) = saved
        W.engine_code_fp(fresh=True)
        shutil.rmtree(tmp, ignore_errors=True)

    js = open(os.path.join(ROOT, "engines", "weaver-core", "gateway_worker.mjs"),
              encoding="utf-8").read()
    check("العمليةُ المقيمةُ تخرج حين يموت خادمُها",
          "const PARENT = process.ppid" in js and "process.kill(PARENT, 0)" in js
          and ".unref()" in js)


if __name__ == "__main__":
    print("fast restart: engine fingerprint · worker exits with its server")
    main()
    print("FAIL: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)
