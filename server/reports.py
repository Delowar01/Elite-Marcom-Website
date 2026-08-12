"""Elite Marcom admin — Site Insights reports (branded PDF + standalone HTML).

Both renderers take the dict from analytics.summary() so the numbers on the
dashboard, in the PDF and in the HTML file are always the same.
"""
from __future__ import annotations

import html as html_mod
import io
import time

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
M = 40.0
ORANGE = (0.941, 0.435, 0.133)
VIOLET = (0.455, 0.404, 0.780)
INK = (0.078, 0.094, 0.122)
GREY = (0.541, 0.561, 0.596)
LINE = (0.910, 0.894, 0.871)
PANEL = (0.976, 0.968, 0.957)

VITAL_LABEL = {"LCP": "Main content shown", "CLS": "Layout stability",
               "INP": "Response to taps", "FCP": "First paint", "TTFB": "Server response"}
VITAL_GOOD = {"LCP": 2500, "CLS": 0.1, "INP": 200, "FCP": 1800, "TTFB": 800}


def _fmt_vital(metric: str, value: float) -> str:
    return str(round(value, 3)) if metric == "CLS" else f"{int(round(value))} ms"


def _period(data: dict) -> str:
    return f"{data.get('start', '')} to {data.get('end', '')}"


def _delta(value) -> str:
    if value is None:
        return ""
    return f"  ({'+' if value >= 0 else ''}{value}% vs previous period)"


# ---------------- PDF ----------------

class _Pdf:
    def __init__(self):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.page = 1
        self.y = PAGE_H - M

    def footer(self):
        self.c.setFont("Helvetica", 7)
        self.c.setFillColorRGB(*GREY)
        self.c.drawString(M, 26, "Elite Marcom — Site Insights · internal report")
        self.c.drawRightString(PAGE_W - M, 26, f"Page {self.page}")

    def need(self, height: float):
        if self.y - height < 54:
            self.footer()
            self.c.showPage()
            self.page += 1
            self.y = PAGE_H - M

    def header(self, data: dict):
        c = self.c
        logo_h = 26.0
        try:
            from .manuals import _logo_path

            logo = ImageReader(str(_logo_path()))
            lw, lh = logo.getSize()
            c.drawImage(logo, M, self.y - logo_h, width=logo_h * lw / lh, height=logo_h,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            c.setFont("Helvetica-Bold", 15)
            c.setFillColorRGB(*INK)
            c.drawString(M, self.y - 16, "ELITE MARCOM")
        c.setFont("Helvetica-Bold", 15)
        c.setFillColorRGB(*INK)
        c.drawRightString(PAGE_W - M, self.y - 8, "Site Insights")
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(*GREY)
        c.drawRightString(PAGE_W - M, self.y - 21, _period(data))
        self.y -= logo_h + 10
        c.setStrokeColorRGB(*ORANGE)
        c.setLineWidth(2)
        c.line(M, self.y, PAGE_W - M, self.y)
        self.y -= 22

    def section(self, title: str):
        self.need(34)
        self.c.setFont("Helvetica-Bold", 10)
        self.c.setFillColorRGB(*ORANGE)
        self.c.drawString(M, self.y - 9, title.upper())
        self.y -= 22

    def kpis(self, cards: list[tuple[str, str, str]]):
        self.need(64)
        c = self.c
        gap = 9.0
        width = (PAGE_W - 2 * M - gap * (len(cards) - 1)) / len(cards)
        top = self.y
        for i, (value, label, note) in enumerate(cards):
            x = M + i * (width + gap)
            c.setFillColorRGB(*PANEL)
            c.setStrokeColorRGB(*LINE)
            c.roundRect(x, top - 56, width, 56, 7, stroke=1, fill=1)
            c.setFont("Helvetica-Bold", 17)
            c.setFillColorRGB(*INK)
            c.drawString(x + 11, top - 27, str(value))
            c.setFont("Helvetica", 7.6)
            c.setFillColorRGB(*GREY)
            c.drawString(x + 11, top - 40, label[:26])
            if note:
                c.setFont("Helvetica", 6.8)
                c.drawString(x + 11, top - 50, note[:30])
        self.y = top - 56 - 18

    def chart(self, series: list[dict]):
        if not series:
            return
        self.need(150)
        c = self.c
        h, w = 112.0, PAGE_W - 2 * M
        top, left = self.y, M
        c.setFillColorRGB(*PANEL)
        c.setStrokeColorRGB(*LINE)
        c.roundRect(left, top - h, w, h, 7, stroke=1, fill=1)
        peak = max([p["views"] for p in series] + [1])
        step = (w - 24) / max(1, len(series) - 1)

        def draw(key, colour, dashed=False):
            c.setStrokeColorRGB(*colour)
            c.setLineWidth(1.6)
            c.setDash(3, 3) if dashed else c.setDash()
            path = c.beginPath()
            for i, point in enumerate(series):
                x = left + 12 + i * step
                y = top - h + 14 + (point[key] / peak) * (h - 30)
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            c.drawPath(path)
            c.setDash()

        draw("views", ORANGE)
        draw("visitors", VIOLET, dashed=True)
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*GREY)
        c.drawString(left + 12, top - h + 4, series[0]["day"])
        c.drawRightString(left + w - 12, top - h + 4, series[-1]["day"])
        c.drawRightString(left + w - 12, top - 10, f"peak {peak} views/day")
        c.setFillColorRGB(*ORANGE)
        c.drawString(left + 12, top - 10, "— pageviews")
        c.setFillColorRGB(*VIOLET)
        c.drawString(left + 74, top - 10, "-- visitors")
        self.y = top - h - 18

    def table(self, title: str, rows: list[dict], value_header: str = "Count",
              empty: str = "No data in this period.", suffix: str = ""):
        self.section(title)
        c = self.c
        if not rows:
            c.setFont("Helvetica-Oblique", 8.5)
            c.setFillColorRGB(*GREY)
            c.drawString(M, self.y - 8, empty)
            self.y -= 22
            return
        peak = max([r["count"] for r in rows] + [1])
        bar_x, bar_w = PAGE_W - M - 150, 100.0
        for row in rows:
            self.need(18)
            label = str(row["label"])
            while stringWidth(label, "Helvetica", 8.5) > bar_x - M - 12 and len(label) > 4:
                label = label[:-2]
            c.setFont("Helvetica", 8.5)
            c.setFillColorRGB(*INK)
            c.drawString(M, self.y - 8, label)
            c.setFillColorRGB(*LINE)
            c.roundRect(bar_x, self.y - 10, bar_w, 5, 2.5, stroke=0, fill=1)
            c.setFillColorRGB(*ORANGE)
            width = max(3.0, bar_w * (row["count"] / peak))
            c.roundRect(bar_x, self.y - 10, width, 5, 2.5, stroke=0, fill=1)
            c.setFont("Helvetica-Bold", 8.5)
            c.setFillColorRGB(*INK)
            c.drawRightString(PAGE_W - M, self.y - 8, f"{row['count']}{suffix}")
            self.y -= 15
        self.y -= 8
        void = value_header

    def paragraph(self, text: str, size: float = 8.5):
        words, line = str(text).split(), ""
        width = PAGE_W - 2 * M
        for word in words:
            probe = (line + " " + word).strip()
            if stringWidth(probe, "Helvetica", size) <= width or not line:
                line = probe
            else:
                self.need(13)
                self.c.setFont("Helvetica", size)
                self.c.setFillColorRGB(*GREY)
                self.c.drawString(M, self.y - 8, line)
                self.y -= 12
                line = word
        if line:
            self.need(13)
            self.c.setFont("Helvetica", size)
            self.c.setFillColorRGB(*GREY)
            self.c.drawString(M, self.y - 8, line)
            self.y -= 12
        self.y -= 6

    def done(self) -> bytes:
        self.footer()
        self.c.save()
        return self.buf.getvalue()


def insights_pdf(data: dict) -> bytes:
    pdf = _Pdf()
    pdf.header(data)
    totals = data.get("totals", {})
    funnel = data.get("funnel", [])
    pdf.kpis([
        (totals.get("views", 0), "Pageviews", _delta(totals.get("viewsChange")).strip("  ")),
        (totals.get("visitors", 0), "Visitors", _delta(totals.get("visitorsChange")).strip("  ")),
        (totals.get("sessions", 0), "Visits", ""),
        (funnel[2]["count"] if len(funnel) > 2 else 0, "Enquiries sent", ""),
        (data.get("manualDownloads", 0), "Manuals downloaded", ""),
    ])
    if data.get("alerts"):
        pdf.section("What needs attention")
        for alert in data["alerts"]:
            pdf.paragraph("•  " + alert.get("text", ""))
    pdf.section("Traffic")
    pdf.chart(data.get("series", []))
    pdf.table("Top pages", data.get("topPages", []))
    pdf.table("Where visitors come from", data.get("referrers", []),
              empty="All visits were direct or unreferred.")
    pdf.table("Countries", data.get("countries", []),
              empty="Country data appears once the site runs behind Cloudflare.")
    pdf.table("Devices", data.get("devices", []))
    pdf.table("Landing pages", data.get("entryPages", []))
    pdf.table("Most viewed products", data.get("products", []),
              empty="No product pages were viewed.")
    pdf.table("What people searched for", data.get("searches", []),
              empty="No catalog searches in this period.")
    pdf.section("From browsing to enquiry")
    for step in funnel:
        base = funnel[0]["count"] if funnel else 0
        rate = "—" if not base else ("starting point" if step is funnel[0]
                                     else f"{step['rate']}% of viewers")
        pdf.paragraph(f"{step['count']}   {step['step']}   ({rate})")
    if data.get("vitals"):
        pdf.section("Speed experienced by real visitors")
        for vital in data["vitals"]:
            good = VITAL_GOOD.get(vital["metric"], 0)
            verdict = "good" if vital["p75"] <= good else "needs work"
            pdf.paragraph(f"{VITAL_LABEL.get(vital['metric'], vital['metric'])} "
                          f"({vital['metric']}): {_fmt_vital(vital['metric'], vital['p75'])} — "
                          f"{verdict}, from {vital['samples']} measurements")
        pdf.table("Slowest pages (average main-content time)", data.get("slowPages", []),
                  empty="", suffix=" ms")
    pdf.section("About this report")
    pdf.paragraph("Measured with Elite Marcom's own first-party analytics. No cookies are used, "
                  "no raw IP address or browser identity is stored, and visitor counting uses a key "
                  "that is renewed every day, so visitors cannot be followed across days or identified.")
    return pdf.done()


# ---------------- standalone HTML ----------------

def _esc(value) -> str:
    return html_mod.escape(str(value))


def _bars(rows: list[dict], empty: str, suffix: str = "") -> str:
    if not rows:
        return f'<p class="empty">{_esc(empty)}</p>'
    peak = max([r["count"] for r in rows] + [1])
    out = ['<div class="bars">']
    for row in rows:
        width = max(2, round(row["count"] / peak * 100))
        out.append(
            f'<div class="bar"><span class="bl">{_esc(row["label"])}</span>'
            f'<span class="bt"><i style="width:{width}%"></i></span>'
            f'<span class="bn">{_esc(row["count"])}{_esc(suffix)}</span></div>')
    out.append("</div>")
    return "".join(out)


def _chart_svg(series: list[dict]) -> str:
    if not series:
        return ""
    w, h, pad = 900, 190, 8
    peak = max([p["views"] for p in series] + [1])
    step = (w - pad * 2) / max(1, len(series) - 1)

    def points(key):
        return " ".join(
            f"{pad + i * step:.1f},{h - pad - (p[key] / peak) * (h - pad * 2):.1f}"
            for i, p in enumerate(series))

    line = points("views")
    area = f"{line} {pad + (len(series) - 1) * step:.1f},{h - pad} {pad},{h - pad}"
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="chart" role="img" '
            f'aria-label="Daily pageviews"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#ed6c26" stop-opacity="0.42"/>'
            '<stop offset="100%" stop-color="#ed6c26" stop-opacity="0.02"/></linearGradient></defs>'
            f'<polygon points="{area}" fill="url(#g)"/>'
            f'<polyline points="{line}" fill="none" stroke="#ed6c26" stroke-width="2.5" '
            'stroke-linejoin="round"/>'
            f'<polyline points="{points("visitors")}" fill="none" stroke="#7467c7" '
            'stroke-width="2" stroke-dasharray="6 5"/></svg>')


def insights_html(data: dict) -> str:
    totals = data.get("totals", {})
    funnel = data.get("funnel", [])
    kpis = [
        (totals.get("views", 0), "Pageviews", _delta(totals.get("viewsChange")).strip()),
        (totals.get("visitors", 0), "Visitors", _delta(totals.get("visitorsChange")).strip()),
        (totals.get("sessions", 0), "Visits", ""),
        (funnel[2]["count"] if len(funnel) > 2 else 0, "Enquiries sent", ""),
        (data.get("manualDownloads", 0), "Manuals downloaded", ""),
    ]
    cards = "".join(
        f'<div class="kpi"><b>{_esc(v)}</b><span>{_esc(label)}</span>'
        + (f'<em>{_esc(note)}</em>' if note else "") + "</div>"
        for v, label, note in kpis)
    alerts = "".join(
        f'<p class="alert alert--{_esc(a.get("level", "warn"))}">{_esc(a.get("text", ""))}</p>'
        for a in data.get("alerts", []))
    base = funnel[0]["count"] if funnel else 0
    steps = "".join(
        f'<div class="step"><b>{_esc(s["count"])}</b><span>{_esc(s["step"])}</span>'
        f'<em>{"—" if not base else ("starting point" if i == 0 else str(s["rate"]) + "% of viewers")}</em></div>'
        for i, s in enumerate(funnel))
    vitals = "".join(
        f'<div class="kpi"><b>{_esc(_fmt_vital(v["metric"], v["p75"]))}'
        f'<i class="{"ok" if v["p75"] <= VITAL_GOOD.get(v["metric"], 0) else "bad"}">'
        f'{"good" if v["p75"] <= VITAL_GOOD.get(v["metric"], 0) else "slow"}</i></b>'
        f'<span>{_esc(VITAL_LABEL.get(v["metric"], v["metric"]))} ({_esc(v["metric"])})</span></div>'
        for v in data.get("vitals", []))
    generated = time.strftime("%d %B %Y, %H:%M UTC", time.gmtime())
    panels = [
        ("Top pages", _bars(data.get("topPages", []), "No pageviews in this period.")),
        ("Where visitors come from", _bars(data.get("referrers", []), "All visits were direct or unreferred.")),
        ("Countries", _bars(data.get("countries", []), "Country data appears once the site runs behind Cloudflare.")),
        ("Devices", _bars(data.get("devices", []), "No device data yet.")),
        ("Landing pages", _bars(data.get("entryPages", []), "No visits recorded.")),
        ("Last page seen", _bars(data.get("exitPages", []), "No visits recorded.")),
        ("Most viewed products", _bars(data.get("products", []), "No product pages were viewed.")),
        ("What people searched for", _bars(data.get("searches", []), "No catalog searches in this period.")),
    ]
    grid = "".join(f'<section class="panel"><h2>{_esc(t)}</h2>{body}</section>' for t, body in panels)
    slow = data.get("slowPages", [])
    slow_block = (f'<section class="panel"><h2>Slowest pages</h2>'
                  f'{_bars(slow, "", " ms")}</section>' if slow else "")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Elite Marcom — Site Insights {_esc(_period(data))}</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;padding:38px 30px 60px;background:#f6f2ec;color:#14181f;
   font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Arial,sans-serif}}
 .wrap{{max-width:1040px;margin:0 auto}}
 header{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;
   border-bottom:3px solid #ed6c26;padding-bottom:14px;margin-bottom:24px;flex-wrap:wrap}}
 .brand{{font-size:1.45rem;font-weight:800;letter-spacing:-0.01em}}
 .brand i{{color:#ed6c26;font-style:normal}}
 .meta{{text-align:right;color:#6b7280;font-size:0.85rem}}
 h1{{font-size:1.05rem;margin:0 0 2px;font-weight:700}}
 h2{{font-size:0.82rem;text-transform:uppercase;letter-spacing:0.1em;color:#6b7280;margin:0 0 12px}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}}
 .kpi{{background:#fff;border:1px solid #e8e4de;border-radius:14px;padding:16px 18px}}
 .kpi b{{display:block;font-size:1.65rem;line-height:1.1}}
 .kpi span{{color:#6b7280;font-size:0.8rem}}
 .kpi em{{display:block;font-style:normal;color:#8a8f98;font-size:0.72rem;margin-top:3px}}
 .kpi i{{font-style:normal;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.08em;
   padding:2px 7px;border-radius:999px;margin-left:7px;vertical-align:middle}}
 .kpi i.ok{{background:#e3f5ea;color:#2f855a}} .kpi i.bad{{background:#fdeaea;color:#c53030}}
 .panel{{background:#fff;border:1px solid #e8e4de;border-radius:16px;padding:20px 22px;margin-bottom:18px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-bottom:18px}}
 .grid .panel{{margin:0}}
 .chart{{width:100%;height:190px;display:block}}
 .legend{{color:#6b7280;font-size:0.8rem;margin:8px 0 0}}
 .legend b{{display:inline-block;width:16px;height:3px;border-radius:2px;vertical-align:middle}}
 .bars{{display:flex;flex-direction:column;gap:8px}}
 .bar{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(70px,1fr) auto;gap:10px;
   align-items:center;font-size:0.86rem}}
 .bl{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#3f4650}}
 .bt{{height:8px;border-radius:99px;background:#eee9e2;overflow:hidden}}
 .bt i{{display:block;height:100%;background:linear-gradient(90deg,#ed6c26,#f18042)}}
 .bn{{font-variant-numeric:tabular-nums;color:#6b7280;font-size:0.8rem}}
 .empty{{color:#8a8f98;font-size:0.85rem;margin:0}}
 .alert{{border:1px solid #d9a441;color:#8a6116;background:#fdf6e7;border-radius:10px;
   padding:10px 14px;margin:0 0 8px;font-size:0.88rem}}
 .alert--good{{border-color:#63c98c;color:#2f855a;background:#eaf7ef}}
 .funnel{{display:flex;gap:12px;flex-wrap:wrap}}
 .step{{flex:1;min-width:150px;background:#faf7f3;border:1px solid #e8e4de;border-radius:12px;padding:14px 16px}}
 .step b{{display:block;font-size:1.4rem}} .step span{{color:#6b7280;font-size:0.8rem}}
 .step em{{display:block;font-style:normal;color:#ed6c26;font-weight:700;font-size:0.78rem;margin-top:3px}}
 footer{{color:#8a8f98;font-size:0.78rem;border-top:1px solid #e8e4de;padding-top:14px;margin-top:26px}}
 @media print{{body{{background:#fff;padding:0}} .panel,.kpi{{break-inside:avoid}}}}
</style></head><body><div class="wrap">
<header><div><div class="brand">ELITE <i>MARCOM</i></div><h1>Site Insights</h1></div>
<div class="meta">{_esc(_period(data))}<br>Generated {_esc(generated)}</div></header>
{alerts}
<div class="kpis">{cards}</div>
<section class="panel"><h2>Traffic</h2>{_chart_svg(data.get("series", []))}
<p class="legend"><b style="background:#ed6c26"></b> Pageviews &nbsp; <b style="background:#7467c7"></b> Visitors</p></section>
<div class="grid">{grid}</div>
<section class="panel"><h2>From browsing to enquiry</h2><div class="funnel">{steps}</div></section>
{f'<section class="panel"><h2>Speed experienced by real visitors</h2><div class="kpis">{vitals}</div></section>' if vitals else ''}
{slow_block}
<footer>Measured with Elite Marcom's own first-party analytics. No cookies are used, no raw IP
address or browser identity is stored, and visitor counting uses a key renewed every day — so
visitors cannot be followed across days or identified.</footer>
</div></body></html>"""
