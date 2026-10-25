"""Printable "report for doctor": cycle table, summary stats, neutral flags.

Everything is computed on the server from the user's own logged periods and returned
in the response only. The wording is deliberately non-diagnostic: flags state a
threshold and what was observed, nothing more.

Reference ranges (stated in the report itself): FIGO normal menstrual-cycle limits
for frequency (24-38 days), regularity (shortest to longest cycle differs by up to
7-9 days, depending on age) and period duration (up to 8 days); cycles outside
21-35 days and a >=7 day spread are widely used practical markers.
"""

from __future__ import annotations

import datetime
import statistics
from html import escape

from app.models import User
from app.services.forecast_service import MAX_CYCLE, MISSED_LOG_RATIO, ForecastService

REF_LOW, REF_HIGH = 21, 35  # reference band used for the flag and the chart
FIGO_FREQ = (24, 38)
FIGO_DURATION_MAX = 8
VARIABILITY_FLAG = 7  # days (max - min) at which the flag appears
VARIABILITY_UPPER = 9  # upper end of the FIGO age-dependent limit
LAST_N = 6
OUT_OF_RANGE_MIN = 2  # flag if at least this many of the last LAST_N are outside
LONG_PERIOD_DAYS = 8
NO_PERIOD_DAYS = 90
MONTHS = (6, 12, 24)

DISCLAIMER = (
    "This report summarises dates you logged yourself. It is not a diagnosis and "
    "does not replace medical advice. Gaps in logging affect every number here. "
    "Please discuss anything that worries you with a healthcare professional."
)


def jsonable(obj):
    """Recursively turn dates into ISO strings (Flask would emit RFC 822)."""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(v) for v in obj]
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


def _round(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(x, nd)


class DoctorReportService:
    @staticmethod
    def build(
        user: User,
        periods: list[tuple[datetime.date, datetime.date | None]],
        months: int = 12,
        today: datetime.date | None = None,
        include_name: bool = False,
    ) -> dict:
        today = today or datetime.date.today()
        model = ForecastService.fit(periods, today)
        rows = model.periods  # sorted, double logs merged
        since = today - datetime.timedelta(days=round(months * 30.4375))

        gaps = [(b[0] - a[0]).days for a, b in zip(rows, rows[1:], strict=False)]
        normal = [g for g in gaps if g <= 50]
        ref = (
            statistics.median(normal)
            if normal
            else (statistics.median(gaps) if gaps else None)
        )

        cycles = []  # every logged period in range, with the cycle that follows it
        excluded = []
        for i, (start, end) in enumerate(rows):
            if start < since or start > today:
                continue
            length = (end - start).days + 1 if end else None
            if end and not 1 <= length <= 60:
                length = None
            nxt = rows[i + 1][0] if i + 1 < len(rows) else None
            cl = (nxt - start).days if nxt else None
            is_missed = bool(
                cl is not None
                and ref is not None
                and (cl >= MISSED_LOG_RATIO * ref or cl > MAX_CYCLE)
            )
            entry = {
                "start": start,
                "end": end,
                "period_days": length,
                "cycle_days": cl,
                "excluded": is_missed,
                "ongoing": end is None and (today - start).days < 14,
            }
            cycles.append(entry)
            if is_missed:
                excluded.append({"start": start, "next_start": nxt, "gap_days": cl})

        used = [
            c["cycle_days"] for c in cycles if c["cycle_days"] and not c["excluded"]
        ]
        plen = [c["period_days"] for c in cycles if c["period_days"]]
        last = used[-LAST_N:]
        stats = {
            "cycles_counted": len(used),
            "mean_cycle_days": _round(statistics.fmean(used)) if used else None,
            "median_cycle_days": _round(statistics.median(used)) if used else None,
            "min_cycle_days": min(used) if used else None,
            "max_cycle_days": max(used) if used else None,
            "sd_cycle_days": _round(statistics.stdev(used)) if len(used) > 1 else None,
            "variability_days": (max(last) - min(last)) if len(last) >= 2 else None,
            "variability_cycles": len(last),
            "max_consecutive_change_days": (
                max(abs(b - a) for a, b in zip(last, last[1:], strict=False))
                if len(last) >= 2
                else None
            ),
            "median_period_days": _round(statistics.median(plen)) if plen else None,
            "periods_counted": len(plen),
        }

        flags = DoctorReportService._flags(cycles, used, last, stats, rows, today)
        return {
            "generated": today,
            "range": {"from": since, "to": today, "months": months},
            "name": user.username if include_name else None,
            "cycles": cycles,
            "stats": stats,
            "flags": flags,
            "excluded_gaps": excluded,
            "reference": {
                "band_days": [REF_LOW, REF_HIGH],
                "figo_frequency_days": list(FIGO_FREQ),
                "figo_variation_days": [7, 9],
                "figo_duration_max_days": FIGO_DURATION_MAX,
            },
            "disclaimer": DISCLAIMER,
        }

    @staticmethod
    def _flags(cycles, used, last, stats, rows, today) -> list[dict]:
        flags = []
        out = [c for c in last if c > REF_HIGH or c < REF_LOW]
        if len(out) >= OUT_OF_RANGE_MIN:
            long_n = sum(c > REF_HIGH for c in out)
            short_n = sum(c < REF_LOW for c in out)
            flags.append(
                {
                    "code": "cycle_length_out_of_range",
                    "threshold": f"at least {OUT_OF_RANGE_MIN} of the last {LAST_N} "
                    f"cycles longer than {REF_HIGH} or shorter than {REF_LOW} days",
                    "observed": f"{len(out)} of the last {len(last)} cycles "
                    f"({long_n} longer than {REF_HIGH}, {short_n} shorter than "
                    f"{REF_LOW} days)",
                }
            )
        var = stats["variability_days"]
        if var is not None and var >= VARIABILITY_FLAG:
            flags.append(
                {
                    "code": "cycle_variability",
                    "threshold": f"difference between the longest and shortest of the "
                    f"last {LAST_N} cycles of {VARIABILITY_FLAG} days or more (a "
                    f"commonly used marker for irregular cycles; FIGO normal "
                    f"variation is up to 7-9 days depending on age)",
                    "observed": f"{var} days over the last {stats['variability_cycles']}"
                    f" cycles"
                    + (
                        f", above the {VARIABILITY_UPPER}-day upper limit"
                        if var > VARIABILITY_UPPER
                        else ""
                    ),
                }
            )
        long_periods = [
            c
            for c in cycles
            if c["period_days"] and c["period_days"] > LONG_PERIOD_DAYS
        ]
        if long_periods:
            flags.append(
                {
                    "code": "long_period",
                    "threshold": f"period lasting more than {LONG_PERIOD_DAYS} days "
                    f"(FIGO normal duration is up to {FIGO_DURATION_MAX} days)",
                    "observed": f"{len(long_periods)} logged period(s), longest "
                    f"{max(c['period_days'] for c in long_periods)} days",
                }
            )
        gaps = [(b[0] - a[0]).days for a, b in zip(rows, rows[1:], strict=False)]
        in_range = {c["start"] for c in cycles}
        long_gaps = [
            g
            for (a, _), g in zip(rows, gaps, strict=False)
            if a in in_range and g > NO_PERIOD_DAYS
        ]
        since_last = (today - rows[-1][0]).days if rows else 0
        last_end = rows[-1][1] if rows else None
        ongoing = (last_end is None and since_last < 14) or (
            last_end is not None and last_end >= today
        )
        if long_gaps or (rows and not ongoing and since_last > NO_PERIOD_DAYS):
            obs = []
            if long_gaps:
                obs.append(f"a gap of {max(long_gaps)} days between logged periods")
            if rows and not ongoing and since_last > NO_PERIOD_DAYS:
                obs.append(f"{since_last} days since the last logged period start")
            flags.append(
                {
                    "code": "no_period_90_days",
                    "threshold": f"more than {NO_PERIOD_DAYS} days without a logged "
                    "period (this can also mean periods were not logged)",
                    "observed": "; ".join(obs),
                }
            )
        missed = [c for c in cycles if c["excluded"]]
        if missed:
            flags.append(
                {
                    "code": "possible_missed_logs",
                    "threshold": f"gap of {MISSED_LOG_RATIO}x the usual cycle length "
                    "or more between two logged periods",
                    "observed": f"{len(missed)} gap(s) left out of the statistics "
                    "(listed below)",
                }
            )
        return flags

    # --- HTML ------------------------------------------------------------------

    @staticmethod
    def chart_svg(data: dict) -> str:
        pts = [
            (c["start"], c["cycle_days"])
            for c in data["cycles"]
            if c["cycle_days"] and not c["excluded"]
        ]
        w, h, left, r, t, b = 640, 220, 40, 12, 12, 30
        if len(pts) < 2:
            return ""
        lo = min(15, min(v for _, v in pts) - 2)
        hi = max(45, max(v for _, v in pts) + 2)

        def y(v):
            return t + (hi - v) * (h - t - b) / (hi - lo)

        n = len(pts)
        x = [left + i * (w - left - r) / (n - 1) for i in range(n)]
        line = " ".join(
            f"{xi:.1f},{y(v):.1f}" for xi, (_, v) in zip(x, pts, strict=True)
        )
        dots = "".join(
            f'<circle cx="{xi:.1f}" cy="{y(v):.1f}" r="3.5" fill="#1b4f72"/>'
            f'<text x="{xi:.1f}" y="{y(v) - 7:.1f}" font-size="10" '
            f'text-anchor="middle">{v}</text>'
            for xi, (_, v) in zip(x, pts, strict=True)
        )
        ticks = "".join(
            f'<text x="{xi:.1f}" y="{h - 12}" font-size="9" text-anchor="middle">'
            f"{d.strftime('%b %y')}</text>"
            for i, (xi, (d, _)) in enumerate(zip(x, pts, strict=True))
            if n <= 8 or i % ((n // 8) + 1) == 0
        )
        grid = "".join(
            f'<line x1="{left}" x2="{w - r}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
            f'stroke="#ccc" stroke-width="0.5"/><text x="{left - 4}" y="{y(v) + 3:.1f}" '
            f'font-size="9" text-anchor="end">{v}</text>'
            for v in range(20, hi, 10)
        )
        return (
            f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Cycle length in days '
            f'for each cycle, with the {REF_LOW} to {REF_HIGH} day reference band" '
            f'width="100%" font-family="sans-serif">'
            f'<rect x="{left}" y="{y(REF_HIGH):.1f}" width="{w - left - r}" '
            f'height="{y(REF_LOW) - y(REF_HIGH):.1f}" fill="#d6eaf8"/>{grid}'
            f'<polyline points="{line}" fill="none" stroke="#1b4f72" '
            f'stroke-width="1.5"/>{dots}{ticks}</svg>'
        )

    @staticmethod
    def render_html(data: dict) -> str:
        e = escape
        s = data["stats"]
        rng = data["range"]

        def v(x, unit=""):
            return "&ndash;" if x is None else f"{e(str(x))}{unit}"

        def row(c):
            note = ""
            if c["excluded"]:
                note = " <em>(gap excluded: possible missed log)</em>"
            elif c["ongoing"]:
                note = " <em>(ongoing)</em>"
            return (
                f"<tr><td>{c['start'].isoformat()}</td>"
                f"<td>{v(c['period_days'])}</td>"
                f"<td>{v(c['cycle_days'])}{note}</td></tr>"
            )

        rows = "".join(row(c) for c in reversed(data["cycles"])) or (
            '<tr><td colspan="3">No periods logged in this range.</td></tr>'
        )
        if data["flags"]:
            flags = "".join(
                f"<li><strong>{e(f['observed'])}.</strong> "
                f"<span>Threshold: {e(f['threshold'])}.</span></li>"
                for f in data["flags"]
            )
        else:
            flags = (
                "<li>Nothing in the logged data crossed the thresholds listed "
                "below.</li>"
            )
        excl = ""
        if data["excluded_gaps"]:
            items = "".join(
                f"<li>{g['start'].isoformat()} to {g['next_start'].isoformat()} "
                f"({g['gap_days']} days)</li>"
                for g in data["excluded_gaps"]
            )
            excl = (
                "<h2>Gaps left out of the statistics</h2><p>These gaps are much longer "
                "than the usual cycle, so a period may not have been logged. They are "
                f"not counted as cycles.</p><ul>{items}</ul>"
            )
        chart = DoctorReportService.chart_svg(data)
        chart_html = (
            f"<h2>Cycle length over time</h2>{chart}"
            f'<p class="small">Shaded band: {REF_LOW}&ndash;{REF_HIGH} days.</p>'
            if chart
            else ""
        )
        who = f" for {e(data['name'])}" if data["name"] else ""
        ref = data["reference"]
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="referrer" content="no-referrer">
<title>Cycle summary{who}</title>
<style>
:root{{color-scheme:light}}
body{{font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
color:#111;background:#fff;margin:0 auto;max-width:780px;padding:16px}}
h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:16px;margin:22px 0 6px;
border-bottom:1px solid #999;padding-bottom:2px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:4px 8px;
text-align:left}}th{{background:#f0f0f0}}
.stats{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}}
.stats div{{border:1px solid #bbb;padding:6px 8px}}.stats b{{display:block;font-size:18px}}
.small{{font-size:12px;color:#444}}.disclaimer{{border:2px solid #111;padding:8px 10px;
margin-top:20px}}li{{margin-bottom:6px}}
.noprint button{{font:inherit;padding:6px 12px}}
@page{{margin:14mm}}
@media print{{body{{max-width:none;padding:0;font-size:11pt}}.noprint{{display:none}}
h2,table,svg,.disclaimer{{break-inside:avoid}}tr{{break-inside:avoid}}}}
</style></head><body>
<h1>Cycle summary{who}</h1>
<p class="small">Period covered: {rng["from"].isoformat()} to {rng["to"].isoformat()}
({rng["months"]} months) &middot; Generated {data["generated"].isoformat()}</p>
<p class="noprint"><button onclick="window.print()">Print</button></p>
<h2>Summary</h2>
<div class="stats">
<div>Cycles counted<b>{v(s["cycles_counted"])}</b></div>
<div>Median cycle<b>{v(s["median_cycle_days"], " d")}</b></div>
<div>Mean cycle<b>{v(s["mean_cycle_days"], " d")}</b></div>
<div>Range<b>{v(s["min_cycle_days"])}&ndash;{v(s["max_cycle_days"])} d</b></div>
<div>Standard deviation<b>{v(s["sd_cycle_days"], " d")}</b></div>
<div>Variability (last {s["variability_cycles"]} cycles)<b>{v(s["variability_days"], " d")}</b></div>
<div>Median period length<b>{v(s["median_period_days"], " d")}</b></div>
</div>
<h2>Observations</h2>
<ul>{flags}</ul>
<p class="small">Reference points used: cycles of {ref["band_days"][0]}&ndash;{ref["band_days"][1]} days;
FIGO normal ranges: frequency {ref["figo_frequency_days"][0]}&ndash;{ref["figo_frequency_days"][1]} days,
variation up to {ref["figo_variation_days"][0]}&ndash;{ref["figo_variation_days"][1]} days between the shortest and longest cycle,
duration up to {ref["figo_duration_max_days"]} days. A spread of 7 days or more is a commonly used marker of irregular cycles.</p>
{chart_html}
<h2>Cycles</h2>
<table><thead><tr><th>Period start</th><th>Period length (days)</th><th>Cycle length (days)</th></tr></thead>
<tbody>{rows}</tbody></table>
{excl}
<p class="disclaimer"><strong>Not a diagnosis.</strong> {e(data["disclaimer"])}</p>
</body></html>"""
