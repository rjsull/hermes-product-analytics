#!/usr/bin/env python3
"""Build metrics and charts from the extracted CSVs. Standard library only.

Reads data/*.csv, writes data/metrics.json and charts/*.svg.

The two things this file is really demonstrating:
  1. A normalized metrics layer: one canonical model name, one session-count
     definition, one cost attribution rule, declared in code where it can be tested.
  2. Metric-shape discipline: session counts are additive, rates are not, and
     session state is as-of. Nothing here averages a ratio over time or sums a
     snapshot across periods.
"""
import csv
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CHARTS = os.path.join(ROOT, "charts")

# --- metrics layer: the only place these rules live -------------------------

def normalize_model(raw):
    """Collapse provider-prefixed and bare model ids to one canonical key.

    'z-ai/glm-5.3-flash:US', 'glm-5-3-flash' and 'glm-5.2-flash' are the same
    model reached through different routes. Untreated, every per-model metric
    splits by routing detail instead of by model.
    """
    m = (raw or "unknown").split("/")[-1]        # strip provider prefix
    m = m.split(":")[0]                          # strip region/serving suffix
    m = m.replace("_", "-").lower()
    m = re.sub(r"(?<=[0-9])\.(?=[0-9])", "-", m)  # 5.3 -> 5-3, v4.1 -> v4-1
    return m


CLEAN_END_REASONS = {"cron_complete"}


def is_clean_end(reason):
    """A session counts as completed only when it ended on purpose."""
    return reason in CLEAN_END_REASONS


def read_csv(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --- tiny SVG charting (no dependencies) -----------------------------------

INK, MUTED, ACCENT, WARN = "#1f2933", "#7b8794", "#2b6cb0", "#b7791f"


def svg_open(w, h, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'font-family="Helvetica,Arial,sans-serif">',
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
            f'<text x="16" y="26" font-size="15" font-weight="bold" fill="{INK}">{html.escape(title)}</text>']


def save_svg(name, parts):
    parts.append("</svg>")
    os.makedirs(CHARTS, exist_ok=True)
    with open(os.path.join(CHARTS, name), "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


def hbar(name, title, pairs, unit="", color=ACCENT):
    """Horizontal bars: [(label, value)] sorted descending by the caller."""
    w, row_h, top, left = 760, 26, 52, 250
    h = top + row_h * len(pairs) + 34
    mx = max([v for _, v in pairs] or [1]) or 1
    p = svg_open(w, h, title)
    for i, (label, val) in enumerate(pairs):
        y = top + i * row_h
        bw = (w - left - 90) * (val / mx)
        p.append(f'<text x="{left - 10}" y="{y + 15}" font-size="12" text-anchor="end" fill="{INK}">'
                 f'{html.escape(str(label))}</text>')
        p.append(f'<rect x="{left}" y="{y + 3}" width="{bw:.1f}" height="15" fill="{color}" opacity="0.85"/>')
        p.append(f'<text x="{left + bw + 8:.1f}" y="{y + 15}" font-size="12" fill="{MUTED}">'
                 f'{val:g}{unit}</text>')
    save_svg(name, p)


def line_chart(name, title, labels, values, unit=""):
    w, h, top, bottom, left, right = 760, 300, 56, 250, 60, 720
    mx = max(values or [1]) or 1
    n = max(len(values), 1)
    step = (right - left) / max(n - 1, 1)
    p = svg_open(w, h, title)
    p.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{MUTED}" stroke-width="1"/>')
    pts = []
    for i, v in enumerate(values):
        x = left + i * step
        y = bottom - (v / mx) * (bottom - top)
        pts.append(f"{x:.1f},{y:.1f}")
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{ACCENT}"/>')
        if n <= 22:
            p.append(f'<text x="{x:.1f}" y="{y - 9:.1f}" font-size="11" text-anchor="middle" fill="{MUTED}">{v:g}</text>')
            p.append(f'<text x="{x:.1f}" y="{bottom + 16}" font-size="9.5" text-anchor="middle" fill="{MUTED}" '
                     f'transform="rotate(-38 {x:.1f} {bottom + 16})">{html.escape(labels[i])}</text>')
    p.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{ACCENT}" stroke-width="2"/>')
    p.append(f'<text x="{left}" y="{top - 14}" font-size="11" fill="{MUTED}">peak {mx:g}{unit}</text>')
    save_svg(name, p)


# --- build ------------------------------------------------------------------

def main():
    sessions = read_csv("sessions.csv")
    calls = read_csv("tool_calls.csv")
    usage = read_csv("model_usage.csv")
    weekly = read_csv("weekly_activity.csv")
    cron = read_csv("cron_executions.csv")
    if not sessions:
        raise SystemExit("no data/sessions.csv; run extract.py first")

    total_sessions = len(sessions)
    clean = [s for s in sessions if is_clean_end(s["end_reason"])]
    reaped = [s for s in sessions if "reap" in s["end_reason"]]
    incomplete = [s for s in sessions if s["end_reason"] == "cron_incomplete_no_output"]
    messages = sum(int(s["messages"]) for s in sessions)
    tool_calls = sum(int(s["tool_calls"]) for s in sessions)
    in_tok = sum(int(s["input_tokens"]) for s in sessions)
    out_tok = sum(int(s["output_tokens"]) for s in sessions)
    cost = sum(float(s["est_cost_usd"] or 0) for s in sessions)

    by_source = {}
    for s in sessions:
        by_source[s["source"]] = by_source.get(s["source"], 0) + 1
    by_end = {}
    for s in sessions:
        by_end[s["end_reason"]] = by_end.get(s["end_reason"], 0) + 1
    by_tool = {}
    for c in calls:
        by_tool[c["tool_name"]] = by_tool.get(c["tool_name"], 0) + 1

    raw_models, norm_models = {}, {}
    for u in usage:
        raw_models[u["model_raw"]] = raw_models.get(u["model_raw"], 0) + int(u["api_calls"] or 0)
        n = normalize_model(u["model_raw"])
        norm_models[n] = norm_models.get(n, 0) + int(u["api_calls"] or 0)

    metrics = {
        "window": {
            "first_session": min(s["started_at"] for s in sessions)[:10],
            "last_session": max(s["started_at"] for s in sessions)[:10],
            "weeks_covered": len(weekly),
        },
        "volume": {
            "sessions_total": total_sessions,
            "sessions_completed_cleanly": len(clean),
            "sessions_ended_by_reap": len(reaped),
            "sessions_incomplete_no_output": len(incomplete),
            "completion_rate": round(len(clean) / total_sessions, 4),
            "abandoned_or_reaped_rate": round((len(reaped) + len(incomplete)) / total_sessions, 4),
            "messages_total": messages,
            "tool_calls_total": tool_calls,
            "tool_calls_per_session": round(tool_calls / total_sessions, 2),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "input_output_ratio": round(in_tok / max(out_tok, 1), 1),
            "cost_usd_estimated": round(cost, 3),
            "cost_per_session_usd": round(cost / total_sessions, 4),
        },
        "mix": {
            "sessions_by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
            "sessions_by_end_reason": dict(sorted(by_end.items(), key=lambda kv: -kv[1])),
            "tool_calls_by_tool": dict(sorted(by_tool.items(), key=lambda kv: -kv[1])),
            "model_api_calls_raw": dict(sorted(raw_models.items(), key=lambda kv: -kv[1])),
            "model_api_calls_normalized": dict(sorted(norm_models.items(), key=lambda kv: -kv[1])),
            "distinct_models_raw": len(raw_models),
            "distinct_models_normalized": len(norm_models),
        },
        "weekly": weekly,
        "definition_notes": [
            "sessions_total counts rows in the session table, including sessions that were reaped.",
            "completion_rate counts only sessions whose end_reason is cron_complete.",
            "cost_usd_estimated sums per-session estimated_cost_usd; it is an estimate, not a bill.",
            "model counts are API calls, not sessions; a session can span more than one model.",
            "rate metrics are reported once per window and never averaged across weeks.",
        ],
    }
    with open(os.path.join(DATA, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    line_chart("weekly_sessions.svg", "Sessions per week", [w["week_start"] for w in weekly],
               [int(w["sessions"]) for w in weekly])
    hbar("sessions_by_source.svg", "Where sessions come from",
         sorted(by_source.items(), key=lambda kv: -kv[1]), unit=" sessions")
    hbar("session_end_reason.svg", "How sessions end", sorted(by_end.items(), key=lambda kv: -kv[1]),
         unit=" sessions", color=WARN)
    hbar("tool_mix.svg", "Tool calls by tool (top 12)",
         sorted(by_tool.items(), key=lambda kv: -kv[1])[:12], unit=" calls")
    hbar("model_identity.svg", "API calls per model, raw strings as stored",
         sorted(raw_models.items(), key=lambda kv: -kv[1]), unit=" calls")
    hbar("model_identity_normalized.svg", "API calls per model, after normalization",
         sorted(norm_models.items(), key=lambda kv: -kv[1]), unit=" calls", color=WARN)
    if cron:
        line_chart("cron_executions.svg", "Scheduled job executions per day",
                   [r["day"][5:] for r in cron], [int(r["executions"]) for r in cron])

    print(json.dumps(metrics["volume"], indent=2))
    print("\ndistinct model strings:", metrics["mix"]["distinct_models_raw"],
          "-> normalized:", metrics["mix"]["distinct_models_normalized"])
    print("charts written to", CHARTS)


if __name__ == "__main__":
    main()
