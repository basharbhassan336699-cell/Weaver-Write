"""
chart_html.py — رسمٌ بيانيٌّ تفاعليٌّ في صفحة HTML واحدة (working module)
========================================================================
Chart.js 4.5.1 موجودةٌ في المشروع (engines/frontend-core/vendored/chartjs.min.js)
ولم يكن شيءٌ يستعملها. هنا تُضمَّن في الصفحة نفسِها مع الخطّ (base64)، فتعمل
بلا إنترنت، وتُفتح داخل Weaver Write أو في أيّ متصفّح:
  · لمسٌ أو مرور ⟵ القيمةُ والنسبة.
  · الضغطُ على عنصرٍ في الدليل ⟵ إخفاؤه وإظهاره.
  · أزرار: نوعُ الرسم (أعمدة/خطّ/دائرة)، جدولُ البيانات، تحميلُ صورة PNG.
العربيُّ من اليمين: الفئةُ الأولى يميناً، والمحورُ يميناً، والدليلُ والتلميحُ
من اليمين — كالرسوم الثابتة (build_chart).

لا شبكة: لا CDN ولا طلبات — كلُّ شيءٍ داخل الملفّ.
"""
from __future__ import annotations

import base64
import html as _html
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
CHARTJS = os.path.join(_ROOT, "engines", "frontend-core", "vendored", "chartjs.min.js")
_FONTS = os.path.join(_ROOT, "engines", "fonts-core")

TYPES = ("bar", "horizontal_bar", "grouped_bar", "stacked_bar", "line", "area",
         "multi_line", "scatter", "pie", "donut", "histogram", "radar")


def _colors(theme_id, n):
    """ألوانُ السلاسل نفسُها التي يرسم بها build_chart."""
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import build_chart as bc
    th = bc._load_theme(theme_id or "academic_navy")
    return th, [c if str(c).startswith("#") else "#" + str(c)
                for c in bc._palette(th, max(1, n))]


def _font_css(font):
    """@font-face بالخطّ نفسِه (من ملفّه) — أو لا شيء إن لم يكن عندنا."""
    if _FONTS not in sys.path:
        sys.path.insert(0, _FONTS)
    try:
        import font_catalog as FC
        e = FC.find_font(font or "Kufyan Arabic Regular")
        if not e.get("bundled") and e.get("stand_in"):
            e = FC.find_font(e["stand_in"])
        out, fam = [], e["family"]
        for w, key in ((400, "regular"), (700, "bold")):
            p = e["files"].get(key)
            if not p or (key == "bold" and p == e["files"].get("regular")):
                continue
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            out.append("@font-face{font-family:'%s';src:url(data:font/ttf;base64,%s) "
                       "format('truetype');font-weight:%d;font-display:swap}"
                       % (fam, b64, w))
        return "\n".join(out), fam
    except Exception:
        return "", None


def _datasets(kind, data, colors):
    """(labels، datasets، نوعُ Chart.js) من مواصفة build_chart نفسِها."""
    labels = [str(x) for x in data.get("labels") or []]
    ser = data.get("series") or {}
    if kind in ("grouped_bar", "stacked_bar", "multi_line"):
        if kind == "multi_line" and not labels:
            labels = [str(x) for x in data.get("x") or []]
        ds = []
        for i, (name, vals) in enumerate(ser.items()):
            c = colors[i % len(colors)]
            d = {"label": str(name), "data": [float(v) for v in vals],
                 "backgroundColor": c, "borderColor": c}
            if kind == "multi_line":
                d.update(fill=False, tension=0.3, pointRadius=4, borderWidth=3)
            ds.append(d)
        return labels, ds, "line" if kind == "multi_line" else "bar"
    if kind == "scatter":
        pts = [{"x": float(x), "y": float(y)} for x, y in
               zip(data.get("x") or [], data.get("y") or [])]
        return [], [{"label": data.get("name", ""), "data": pts,
                     "backgroundColor": colors[0], "pointRadius": 6}], "scatter"
    if kind == "histogram":
        vals = [float(v) for v in data.get("values") or []]
        bins = int(data.get("bins") or 10)
        if not vals:
            return [], [], "bar"
        lo, hi = min(vals), max(vals)
        w = (hi - lo) / bins or 1
        counts = [0] * bins
        for v in vals:
            counts[min(bins - 1, int((v - lo) / w))] += 1
        labels = ["%g–%g" % (round(lo + i * w, 2), round(lo + (i + 1) * w, 2))
                  for i in range(bins)]
        return labels, [{"label": data.get("name", ""), "data": counts,
                         "backgroundColor": colors[0]}], "bar"
    vals = [float(v) for v in (data.get("values") or data.get("y") or [])]
    if not labels and data.get("x"):
        labels = [str(x) for x in data["x"]]
    if kind in ("pie", "donut"):
        return labels, [{"data": vals, "backgroundColor": colors[:len(vals)],
                         "borderColor": "#ffffff", "borderWidth": 2}], \
            ("doughnut" if kind == "donut" else "pie")
    if kind in ("line", "area"):
        return labels, [{"label": data.get("name", ""), "data": vals,
                         "borderColor": colors[0], "backgroundColor": colors[0] + "33",
                         "fill": kind == "area", "tension": 0.3, "pointRadius": 5,
                         "borderWidth": 3}], "line"
    if kind == "radar":
        return labels, [{"label": data.get("name", ""), "data": vals,
                         "borderColor": colors[0], "backgroundColor": colors[0] + "40",
                         "pointBackgroundColor": colors[0]}], "radar"
    return labels, [{"label": data.get("name", ""), "data": vals,
                     "backgroundColor": colors[:len(vals)] if len(vals) <= len(colors)
                     else colors[0], "borderRadius": 6}], "bar"


def build_chart_html(spec, out, lang="ar", font=None):
    """صفحةُ رسمٍ تفاعليّة. spec مثل build_chart: {type, data, title, xlabel,
    ylabel, theme, subtitle, source}. يعيد dict {ok, output_path, type}."""
    kind = str(spec.get("type") or "bar")
    if kind not in TYPES:
        return {"ok": False, "error": "unknown chart type: %s" % kind}
    if not os.path.isfile(CHARTJS):
        return {"ok": False, "error": "chart.js missing: %s" % CHARTJS}
    data = spec.get("data") or {}
    n = max(len(data.get("values") or data.get("labels") or []),
            len(data.get("series") or {}), 1)
    th, colors = _colors(spec.get("theme") or spec.get("theme_id"), n)
    try:
        labels, ds, cjs = _datasets(kind, data, colors)
    except (TypeError, ValueError) as e:
        return {"ok": False, "error": "bad data: %s" % e}
    if not ds or not any(d.get("data") for d in ds):
        return {"ok": False, "error": "no data"}
    rtl = lang == "ar"
    # الخطّ: المطلوب، أو Kufyan للعربيّ؛ والإنجليزيُّ بلا طلب ⟵ خطُّ المتصفّح
    css_font, fam = _font_css(font) if (font or rtl) else ("", None)
    stack = kind == "stacked_bar"
    horiz = kind == "horizontal_bar"
    categorical = cjs in ("bar", "line") and kind not in ("histogram",)
    cfg = {
        "type": cjs, "labels": labels, "datasets": ds, "rtl": rtl, "stack": stack,
        "horiz": horiz, "categorical": categorical, "kind": kind,
        "xlabel": spec.get("xlabel", ""), "ylabel": spec.get("ylabel", ""),
        "text": "#" + th["text"].lstrip("#"), "primary": "#" + th["primary"].lstrip("#"),
        "font": fam or "sans-serif",
        "switchable": kind in ("bar", "line", "area", "pie", "donut"),
        "colors": colors,
    }
    L = (dict(bar="أعمدة", line="خطّ", pie="دائرة", table="البيانات", png="تحميل صورة",
              hint="المس عنصراً لترى قيمتَه · اضغط على الدليل لإخفاء سلسلة",
              cat="الفئة", val="القيمة", src="المصدر")
         if rtl else
         dict(bar="Bars", line="Line", pie="Pie", table="Data", png="Download PNG",
              hint="Tap an item to see its value · tap the legend to hide a series",
              cat="Category", val="Value", src="Source"))
    title = _html.escape(str(spec.get("title") or ""))
    sub = _html.escape(str(spec.get("subtitle") or ""))
    src = _html.escape(str(spec.get("source") or ""))
    page = _PAGE % {
        "dir": "rtl" if rtl else "ltr", "lang": "ar" if rtl else "en",
        "title": title, "sub": sub,
        "src": ('<p class="src">%s: %s</p>' % (L["src"], src)) if src else "",
        "fontcss": css_font, "font": _html.escape(fam or "sans-serif"),
        "bg": "#" + th["bg"].lstrip("#"), "text": cfg["text"], "primary": cfg["primary"],
        "accent": "#" + th["accent"].lstrip("#"),
        "chartjs": open(CHARTJS, encoding="utf-8").read().replace("</script", "<\\/script"),
        "cfg": json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/"),
        "L": json.dumps(L, ensure_ascii=False),
        "btns": "".join(
            '<button data-t="%s">%s</button>' % (k, L[k]) for k in ("bar", "line", "pie")
        ) if cfg["switchable"] else "",
        "tbl": L["table"], "png": L["png"], "hint": L["hint"],
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return {"ok": True, "output_path": out, "type": kind, "font": fam,
            "theme": th.get("primary")}


_PAGE = """<!doctype html>
<html lang="%(lang)s" dir="%(dir)s"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<style>
%(fontcss)s
:root{--bg:%(bg)s;--text:%(text)s;--primary:%(primary)s;--accent:%(accent)s}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:'%(font)s',sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:18px 16px 28px}
h1{font-size:clamp(20px,4.5vw,30px);margin:4px 0 2px;color:var(--primary)}
.sub{margin:0 0 10px;opacity:.75}
.bar{width:64px;height:5px;background:var(--accent);border-radius:3px;margin:6px 0 14px}
.tools{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.tools button{font:inherit;font-size:14px;padding:7px 14px;border-radius:20px;cursor:pointer;
 border:1.5px solid var(--primary);background:transparent;color:var(--primary)}
.tools button.on{background:var(--primary);color:#fff}
.card{background:#fff;border-radius:14px;padding:14px;box-shadow:0 2px 14px rgba(0,0,0,.08)}
.chart{position:relative;height:min(62vh,480px)}
.hint{font-size:12px;opacity:.6;margin:8px 2px 0}
table{border-collapse:collapse;width:100%%;margin-top:12px;font-size:14px}
th,td{padding:7px 10px;border-bottom:1px solid #e5e5e5;text-align:start}
th{background:var(--primary);color:#fff}
.src{font-size:12px;opacity:.65;margin-top:10px}
[hidden]{display:none}
</style></head><body><div class="wrap">
<h1>%(title)s</h1><p class="sub">%(sub)s</p><div class="bar"></div>
<div class="tools">%(btns)s<button data-a="table">%(tbl)s</button><button data-a="png">%(png)s</button></div>
<div class="card"><div class="chart"><canvas id="c"></canvas></div>
<div id="tbl" hidden></div></div>
<p class="hint">%(hint)s</p>%(src)s
</div>
<script>%(chartjs)s</script>
<script>
(function(){
// الحزمةُ المضمَّنة تضع الصنفَ في window.Chart ثمّ يعيد سطرُها الأوّل تعريفَه
// حاويةً {default: Chart} — مقيسٌ في المتصفّح. فالصنفُ هو default إن وُجد.
var Chart = (window.Chart && window.Chart["default"]) ? window.Chart["default"] : window.Chart;
window.WeaverChart = Chart;
var C=%(cfg)s, L=%(L)s, chart=null, cur=C.type;
Chart.defaults.font.family="'"+C.font+"',sans-serif"; Chart.defaults.font.size=14;
Chart.defaults.color=C.text;
function fmt(v){return (typeof v==='number')?v.toLocaleString('en'):v;}
function opts(t){
  var round=(t==='pie'||t==='doughnut'), o={responsive:true,maintainAspectRatio:false,
   locale:'en', animation:{duration:500},
   plugins:{legend:{display:round||C.datasets.length>1, position:'bottom', rtl:C.rtl,
     textDirection:C.rtl?'rtl':'ltr', labels:{usePointStyle:true,padding:16}},
    tooltip:{rtl:C.rtl, textDirection:C.rtl?'rtl':'ltr', padding:10,
     callbacks:{label:function(ctx){
       var v=ctx.parsed; v=(v&&typeof v==='object')?(C.horiz?v.x:v.y):v;
       if(t==='scatter') return '('+fmt(ctx.parsed.x)+', '+fmt(ctx.parsed.y)+')';
       var s=(ctx.dataset.label?ctx.dataset.label+': ':'')+fmt(v);
       if(round){var tot=ctx.dataset.data.reduce(function(a,b){return a+b},0);
         s+='  ('+(100*v/tot).toFixed(1)+'%%)';}
       return s;}}}}};
  if(!round && t!=='radar'){
    var cat={reverse:C.rtl && C.categorical, stacked:C.stack, grid:{display:false},
             title:{display:!!C.xlabel,text:C.xlabel}};
    var val={position:C.rtl?'right':'left', stacked:C.stack, beginAtZero:true,
             title:{display:!!C.ylabel,text:C.ylabel}};
    if(C.horiz){ o.indexAxis='y'; cat.position=C.rtl?'right':'left'; cat.reverse=false;
      val.reverse=C.rtl; val.position='bottom'; o.scales={x:val,y:cat}; }
    else if(t==='scatter'){ val.beginAtZero=false;
      o.scales={x:{position:'bottom',title:{display:!!C.xlabel,text:C.xlabel}},y:val}; }
    else o.scales={x:cat,y:val};
  }
  return o;
}
function data(t){
  var ds=JSON.parse(JSON.stringify(C.datasets));
  if(t==='pie'||t==='doughnut'){ ds=[{data:ds[0].data,backgroundColor:C.colors.slice(0,ds[0].data.length),
     borderColor:'#fff',borderWidth:2}]; }
  else if(cur!==C.type && t==='bar'){ ds.forEach(function(d,i){d.backgroundColor=C.datasets.length>1?C.colors[i]:C.colors.slice(0,d.data.length);d.fill=false;}); }
  else if(cur!==C.type && t==='line'){ ds.forEach(function(d,i){var c=C.colors[i]; d.borderColor=c; d.backgroundColor=c; d.fill=false; d.tension=.3; d.borderWidth=3; d.pointRadius=5;}); }
  return {labels:C.labels, datasets:ds};
}
function draw(t){
  if(chart) chart.destroy(); cur=t;
  chart=new Chart(document.getElementById('c'),{type:t,data:data(t),options:opts(t)});
  document.querySelectorAll('[data-t]').forEach(function(b){
    var on=(b.getAttribute('data-t')===t)||(b.getAttribute('data-t')==='pie'&&t==='doughnut');
    b.classList.toggle('on',on);});
}
function table(){
  var h='<table><tr><th>'+L.cat+'</th>';
  C.datasets.forEach(function(d){h+='<th>'+(d.label||L.val)+'</th>';});
  h+='</tr>';
  var rows=C.labels.length?C.labels:C.datasets[0].data.map(function(_,i){return i+1;});
  rows.forEach(function(lab,i){h+='<tr><td>'+lab+'</td>';
    C.datasets.forEach(function(d){var v=d.data[i]; h+='<td>'+(v&&typeof v==='object'?'('+v.x+', '+v.y+')':fmt(v))+'</td>';});
    h+='</tr>';});
  return h+'</table>';
}
document.querySelectorAll('[data-t]').forEach(function(b){b.onclick=function(){
  var t=b.getAttribute('data-t'); if(t==='pie' && C.type==='doughnut') t='doughnut'; draw(t);};});
document.querySelector('[data-a=table]').onclick=function(){
  var el=document.getElementById('tbl'); if(el.hidden){el.innerHTML=table();el.hidden=false;}
  else el.hidden=true;};
document.querySelector('[data-a=png]').onclick=function(){
  var a=document.createElement('a'); a.href=chart.toBase64Image('image/png',1);
  a.download=(document.title||'chart')+'.png'; document.body.appendChild(a); a.click(); a.remove();};
var go=function(){draw(C.type);};
if(document.fonts&&document.fonts.ready) document.fonts.ready.then(go); else go();
})();
</script></body></html>
"""
