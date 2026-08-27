"""
viz_utils.py

Shared formatting + static-SVG chart helpers used by every narrative-style
HTML builder (08, 11, 14). Extracted out of reporting/08_build_narrative_deck.py --
which was the only place these lived -- so a third HTML builder (14) doesn't
copy-paste a third version. This is the same "pull it into one shared module"
fix already applied to pnl_utils.py after duplicated classification logic
shipped a real bug twice; keeping the same discipline here before it happens
to a chart helper instead.

Deliberately holds only pure functions/formatting constants, not HTML
template shells -- 09 uses str.format() (`{{ }}` escaping) and 12 uses
f-strings, so hoisting a shared *template* would fight one convention or the
other. Chart-generating functions have no braces to escape either way, so
they hoist cleanly.

Follows the data-visualization skill (see 09's original docstring for the
full rationale): position/length encodings only, fixed-order categorical
hues via CSS var(), every chart has role="img" + aria-label, numbers also
appear in surrounding prose/tables so a static page doesn't hide data behind
hover-only interaction.
"""


def index_to_quarter(idx: int) -> str:
    year = 2023 + idx // 4
    qtr = idx % 4 + 1
    return f"Q{qtr} {year}"


def fmt_money(x, decimals=1):
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 1e9:
        return f"{sign}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:.{decimals}f}M"
    if a >= 1e3:
        return f"{sign}${a/1e3:.0f}K"
    return f"{sign}${a:.0f}"


def fmt_pct(x):
    return f"{x*100:.1f}%"


def fmt_x(x):
    return f"{x:.2f}x"


def data_table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="mini-table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


# ---------------------------------------------------------------------------
# SVG chart helpers -- static markup, theme-reactive via CSS var() in style=
# ---------------------------------------------------------------------------

def svg_line_chart(series, x_labels, seam_index=None, width=860, height=300, value_fmt=fmt_money, aria_label=""):
    """series: list of (key_unused, label, css_color_var, values) tuples, all same length as x_labels."""
    ML, MR, MT, MB = 58, 20, 16, 40
    plot_w, plot_h = width - ML - MR, height - MT - MB
    n = len(x_labels)
    all_vals = [v for _, _, _, vals in series for v in vals]
    y_max = max(0, max(all_vals)) * 1.12 or 1
    y_min = min(0, min(all_vals)) * 1.12

    def x(i):
        return ML + (plot_w / 2 if n == 1 else (i / (n - 1)) * plot_w)

    def y(v):
        return MT + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{aria_label}">']

    if seam_index and 0 < seam_index < n:
        band_x = x(seam_index) - (x(seam_index) - x(seam_index - 1)) / 2
        parts.append(f'<rect class="seam-band" x="{band_x:.1f}" y="{MT}" width="{(width - MR) - band_x:.1f}" height="{plot_h}"/>')
        parts.append(f'<text class="seam-label" x="{band_x+4:.1f}" y="{MT+12}">Forecast &rarr;</text>')

    for frac in (0.25, 0.5, 0.75, 1.0):
        v = y_min + (y_max - y_min) * frac
        gy = y(v)
        parts.append(f'<line class="gridline" x1="{ML}" x2="{width-MR}" y1="{gy:.1f}" y2="{gy:.1f}"/>')
        parts.append(f'<text class="axis-text" x="{ML-8}" y="{gy+3:.1f}" text-anchor="end">{value_fmt(v)}</text>')
    parts.append(f'<line class="axis-line" x1="{ML}" x2="{width-MR}" y1="{MT+plot_h}" y2="{MT+plot_h}"/>')

    label_step = max(1, -(-n // 9))
    for i, lab in enumerate(x_labels):
        if i % label_step == 0 or i == n - 1:
            parts.append(f'<text class="axis-text" x="{x(i):.1f}" y="{height-14}" text-anchor="middle">{lab}</text>')

    for _, label, color_var, vals in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        parts.append(f'<polyline class="series-line" points="{pts}" style="stroke:var({color_var})"/>')
        for i, v in enumerate(vals):
            parts.append(f'<circle class="series-dot" cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" style="fill:var({color_var})"/>')

    # End labels: drawn after all lines, with a greedy vertical-separation pass
    # so two series ending at similar values (e.g. Gross Profit and
    # Contribution Profit, often close together) don't render as overlapping,
    # illegible text.
    last_x = min(x(n - 1) + 6, width - MR - 2)
    label_positions = sorted(
        [{"color": color_var, "text": value_fmt(vals[-1]), "y": y(vals[-1])} for _, _, color_var, vals in series],
        key=lambda d: d["y"],
    )
    min_gap = 13
    for i in range(1, len(label_positions)):
        if label_positions[i]["y"] - label_positions[i - 1]["y"] < min_gap:
            label_positions[i]["y"] = label_positions[i - 1]["y"] + min_gap
    for lp in label_positions:
        parts.append(f'<text class="series-end-label" x="{last_x:.1f}" y="{lp["y"]+3:.1f}" style="fill:var({lp["color"]})">{lp["text"]}</text>')

    parts.append("</svg>")
    return "".join(parts)


def svg_diverging_bar_chart(bars, width=760, row_h=32, aria_label=""):
    """bars: list of (label, value) tuples. Diverging blue(+)/red(-), sorted as given."""
    ML, MR, MT, MB = 150, 80, 8, 8
    h = MT + MB + len(bars) * row_h
    plot_w = width - ML - MR
    max_abs = max(1, max(abs(v) for _, v in bars))
    zero_x = ML + plot_w / 2
    scale = (plot_w / 2) / max_abs

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {h}" role="img" aria-label="{aria_label}">']
    parts.append(f'<line class="axis-line" x1="{zero_x}" x2="{zero_x}" y1="0" y2="{h}"/>')
    for i, (label, v) in enumerate(bars):
        cy = MT + i * row_h + row_h / 2
        bar_w = abs(v) * scale
        bar_x = zero_x if v >= 0 else zero_x - bar_w
        color_var = "--blue" if v >= 0 else "--red"
        parts.append(f'<text class="axis-text" x="{ML-8}" y="{cy+4:.1f}" text-anchor="end">{label}</text>')
        parts.append(f'<rect x="{bar_x:.1f}" y="{cy-9:.1f}" width="{max(bar_w,1):.1f}" height="18" rx="3" style="fill:var({color_var})"/>')
        label_x = bar_x + bar_w + 6 if v >= 0 else bar_x - 6
        anchor = "start" if v >= 0 else "end"
        parts.append(f'<text class="bar-value-label" x="{label_x:.1f}" y="{cy+4:.1f}" text-anchor="{anchor}">{fmt_money(v) if abs(v) > 100 else fmt_x(v)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_stacked_area(x_labels, series, width=860, height=280, aria_label=""):
    """series: list of (label, css_color_var, values 0-100 pct) -- stacked to 100%."""
    ML, MR, MT, MB = 20, 20, 16, 40
    plot_w, plot_h = width - ML - MR, height - MT - MB
    n = len(x_labels)

    def x(i):
        return ML + (plot_w / 2 if n == 1 else (i / (n - 1)) * plot_w)

    def y(v):
        return MT + plot_h - (v / 100) * plot_h

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{aria_label}">']
    cum_prev = [0] * n
    for label, color_var, vals in series:
        cum_now = [cum_prev[i] + vals[i] for i in range(n)]
        top_pts = " ".join(f"{x(i):.1f},{y(cum_now[i]):.1f}" for i in range(n))
        bot_pts = " ".join(f"{x(n-1-i):.1f},{y(cum_prev[n-1-i]):.1f}" for i in range(n))
        parts.append(f'<polygon points="{top_pts} {bot_pts}" style="fill:var({color_var})" opacity="0.85"/>')
        cum_prev = cum_now

    for frac in (0, 0.5, 1.0):
        gy = y(frac * 100)
        parts.append(f'<text class="axis-text" x="{ML}" y="{gy-3:.1f}">{int(frac*100)}%</text>')
    label_step = max(1, -(-n // 8))
    for i, lab in enumerate(x_labels):
        if i % label_step == 0 or i == n - 1:
            parts.append(f'<text class="axis-text" x="{x(i):.1f}" y="{height-14}" text-anchor="middle">{lab}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_cohort_chart(series, width=860, height=300, aria_label="", y_axis_label=""):
    """series: list of (key_unused, label, css_color_var, values, qsbs) tuples --
    each series can have its own x-domain (vintages of different ages), unlike
    svg_line_chart which assumes one shared x_labels axis for all series.

    y_axis_label: what the y-axis measures (e.g. "Contribution Profit per
    Account ($)") -- this chart's color key is repurposed for vintage
    identity (see end_labels below), not metric identity like svg_line_chart's
    legend row, so without an explicit axis title the y-axis is otherwise
    unlabeled."""
    ML, MT, MB = 58, 16, 40
    # Right margin must fit the widest end-of-line label -- these are full
    # text phrases ("Oldest (Q1 2023)"), not short $ figures like
    # svg_line_chart's end-labels, so a fixed margin clips longer labels.
    # Sized from the actual label text rather than a hardcoded guess.
    longest_label = max((len(label) for _, label, *_ in series), default=0)
    MR = max(20, 14 + longest_label * 6.6)
    plot_w, plot_h = width - ML - MR, height - MT - MB
    all_qsb = [q for *_, qsbs in series for q in qsbs]
    all_vals = [v for _, _, _, vals, _ in series for v in vals]
    qsb_max = max(all_qsb)
    y_max = max(0, max(all_vals)) * 1.15 or 1
    y_min = min(0, min(all_vals)) * 1.15

    def x(q):
        return ML + (q / qsb_max) * plot_w if qsb_max else ML

    def y(v):
        return MT + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{aria_label}">']
    parts.append(f'<line class="gridline" x1="{ML}" x2="{width-MR}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    parts.append(f'<text class="axis-text" x="{ML-8}" y="{y(0)+3:.1f}" text-anchor="end">{fmt_money(0)}</text>')
    for frac in (0.5, 1.0):
        v = y_max * frac
        gy = y(v)
        parts.append(f'<line class="gridline" x1="{ML}" x2="{width-MR}" y1="{gy:.1f}" y2="{gy:.1f}"/>')
        parts.append(f'<text class="axis-text" x="{ML-8}" y="{gy+3:.1f}" text-anchor="end">{fmt_money(v)}</text>')
    parts.append(f'<line class="axis-line" x1="{ML}" x2="{width-MR}" y1="{MT+plot_h}" y2="{MT+plot_h}"/>')
    for q in range(0, qsb_max + 1, max(1, qsb_max // 8)):
        parts.append(f'<text class="axis-text" x="{x(q):.1f}" y="{height-14}" text-anchor="middle">{q}</text>')
    parts.append(f'<text class="axis-text" x="{(ML+width-MR)/2:.1f}" y="{height-2}" text-anchor="middle">Quarters Since Book</text>')
    if y_axis_label:
        ay = MT + plot_h / 2
        parts.append(f'<text class="axis-text" x="14" y="{ay:.1f}" text-anchor="middle" transform="rotate(-90 14 {ay:.1f})">{y_axis_label}</text>')

    end_labels = []
    for _, label, color_var, vals, qsbs in series:
        pts = " ".join(f"{x(q):.1f},{y(v):.1f}" for q, v in zip(qsbs, vals))
        parts.append(f'<polyline class="series-line" points="{pts}" style="stroke:var({color_var})"/>')
        lx, ly = x(qsbs[-1]), y(vals[-1])
        parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" style="fill:var({color_var})"/>')
        end_labels.append({"x": min(lx + 6, width - MR - 2), "y": ly, "color": color_var, "text": label})
    # Same greedy vertical-separation pass as svg_line_chart, in case two
    # vintages' final values land close together.
    end_labels.sort(key=lambda d: d["y"])
    for i in range(1, len(end_labels)):
        if end_labels[i]["y"] - end_labels[i - 1]["y"] < 13:
            end_labels[i]["y"] = end_labels[i - 1]["y"] + 13
    for lbl in end_labels:
        parts.append(f'<text class="series-end-label" x="{lbl["x"]:.1f}" y="{lbl["y"]+3:.1f}" style="fill:var({lbl["color"]})">{lbl["text"]}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Static architecture diagrams -- hand-authored inline SVG (a handful of
# boxes/arrows, not worth a diagram library). Originally built once for
# pitch_deck.html; hoisted here so reporting/14_build_unified_narrative.py's condensed
# "working model" chapter reuses the exact same diagrams rather than a third
# hand-copied version drifting out of sync with the technical deck's.
# ---------------------------------------------------------------------------

ARCHITECTURE_DIAGRAM_SVG = """<svg class="diagram" viewBox="0 0 900 220" role="img" aria-label="Architecture diagram: drivers feed a rate curve library, which multiplies out to P&amp;L dollar lines">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" style="fill:var(--muted)"/>
      </marker>
    </defs>
    <g font-family="inherit" font-size="13.5">
      <rect x="20" y="70" width="190" height="80" rx="10" style="fill:var(--blue);stroke:var(--blue)" opacity="0.12"/>
      <text x="115" y="100" text-anchor="middle" font-weight="700" style="fill:var(--blue)">Drivers</text>
      <text x="115" y="120" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">New Accounts, Balances,</text>
      <text x="115" y="135" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">Volume &mdash; chain-ladder curves</text>

      <line x1="210" y1="110" x2="290" y2="110" style="stroke:var(--muted)" stroke-width="1.5" marker-end="url(#arrow)"/>

      <rect x="300" y="70" width="220" height="80" rx="10" style="fill:var(--orange);stroke:var(--orange)" opacity="0.12"/>
      <text x="410" y="100" text-anchor="middle" font-weight="700" style="fill:var(--orange)">Rate curve library</text>
      <text x="410" y="120" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">$ line &divide; driver, by cohort age</text>
      <text x="410" y="135" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">(loss rate, yield, interchange rate...)</text>

      <line x1="520" y1="110" x2="600" y2="110" style="stroke:var(--muted)" stroke-width="1.5" marker-end="url(#arrow)"/>

      <rect x="610" y="70" width="270" height="80" rx="10" style="fill:var(--aqua);stroke:var(--aqua)" opacity="0.12"/>
      <text x="745" y="100" text-anchor="middle" font-weight="700" style="fill:var(--aqua)">P&amp;L dollar lines</text>
      <text x="745" y="120" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">rate &times; forecasted driver</text>
      <text x="745" y="135" text-anchor="middle" style="fill:var(--ink-2)" font-size="11.5">&rarr; Gross Revenue, Cost of Sales, ...</text>

      <text x="450" y="20" text-anchor="middle" style="fill:var(--muted)" font-size="12">One mechanism handles a genuinely flat rate (yield, ~6.05%/quarter) and a genuinely curving one</text>
      <text x="450" y="36" text-anchor="middle" style="fill:var(--muted)" font-size="12">(loss rate, rising from 0% toward a plateau near quarter 9&ndash;13) without hand-coding which is which.</text>
    </g>
  </svg>"""

BACKBOOK_FRONTBOOK_DIAGRAM_SVG = """<svg class="diagram" viewBox="0 0 380 240" role="img" aria-label="Backbook cohorts anchored to last actual and grown forward; frontbook cohorts seeded from a growth trend and grown on the same curve">
      <g font-family="inherit" font-size="12">
        <text x="10" y="20" font-weight="700" style="fill:var(--blue)">Backbook</text>
        <line x1="10" y1="60" x2="130" y2="60" style="stroke:var(--blue)" stroke-width="2"/>
        <circle cx="130" cy="60" r="4" style="fill:var(--blue)"/>
        <line x1="130" y1="60" x2="230" y2="45" style="stroke:var(--blue)" stroke-width="2" stroke-dasharray="4,3"/>
        <text x="10" y="80" style="fill:var(--ink-2)" font-size="11">actual history</text>
        <text x="140" y="42" style="fill:var(--ink-2)" font-size="11">curve-forecast</text>

        <text x="10" y="130" font-weight="700" style="fill:var(--orange)">Frontbook</text>
        <circle cx="30" cy="170" r="4" style="fill:var(--orange)"/>
        <line x1="30" y1="170" x2="230" y2="150" style="stroke:var(--orange)" stroke-width="2" stroke-dasharray="4,3"/>
        <text x="10" y="190" style="fill:var(--ink-2)" font-size="11">seeded from</text>
        <text x="10" y="203" style="fill:var(--ink-2)" font-size="11">growth trend</text>
        <text x="140" y="143" style="fill:var(--ink-2)" font-size="11">same curve library</text>
      </g>
    </svg>"""
