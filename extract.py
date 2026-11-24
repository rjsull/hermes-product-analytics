#!/usr/bin/env python3
"""Extract privacy-scrubbed session aggregates from the local Hermes Agent store.

Reads the local state database read-only and writes aggregate CSVs into data/.

EXCLUDED BY CONSTRUCTION (never read, never written):
  message content, session titles, session keys, chat/channel ids, display names,
  user ids, working directory, system prompts, tool-name hashes, message ids,
  cron job names, cron job ids, cron job prompts, cron output files.

Session identifiers are replaced with sequential pseudonyms (s001, s002, ...)
ordered by start time, so rows stay joinable inside this repo and meaningless
outside it.

Usage:
  python3 extract.py                     # uses ~/.hermes/state.db
  HERMES_STATE_DB=/path/state.db python3 extract.py
"""
import csv
import datetime as dt
import os
import sqlite3
import sys

STATE_DB = os.environ.get("HERMES_STATE_DB", os.path.expanduser("~/.hermes/state.db"))
CRON_DB = os.environ.get("HERMES_CRON_DB", os.path.expanduser("~/.hermes/cron/executions.db"))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Surface labels are deliberately generic. The gateway that a session arrived
# through is not analytically interesting, and naming it would put a personal
# communication channel into a public repo for no gain.
SOURCE_LABELS = {
    "cron": "scheduled",
    "local": "local_cli",
    "desktop": "desktop_app",
    "signal": "messaging_gateway",
    "gateway": "messaging_gateway",
}


def label_source(value):
    return SOURCE_LABELS.get((value or "").lower(), "other")



def iso(ts):
    if ts is None:
        return ""
    try:
        return dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return ""


def iso_any(v):
    """Accepts epoch numbers or ISO strings; always returns ISO UTC."""
    if v in (None, ""):
        return ""
    s = str(v)
    if s.replace(".", "", 1).isdigit():
        return iso(float(s))
    try:
        return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return ""


def write_csv(name, rows, fields):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  {name:22} {len(rows):>6} rows")
    return rows


def main():
    if not os.path.exists(STATE_DB):
        sys.exit(f"state db not found: {STATE_DB}")
    os.makedirs(OUT, exist_ok=True)
    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    cur = con.cursor()

    # ---- sessions: pseudonymize ids, drop every identifying column ----
    raw = cur.execute(
        """select id, source, model, started_at, ended_at, end_reason,
                  message_count, tool_call_count, api_call_count,
                  input_tokens, output_tokens, cache_read_tokens, reasoning_tokens,
                  estimated_cost_usd, cost_status
           from sessions order by started_at"""
    ).fetchall()
    keys = {}
    sessions = []
    for i, r in enumerate(raw, 1):
        key = f"s{i:03d}"
        keys[r[0]] = key
        start, end = r[3], r[4]
        sessions.append({
            "session_key": key,
            "source": label_source(r[1]),
            "model_raw": r[2] or "unknown",
            "started_at": iso(start),
            "ended_at": iso(end),
            "duration_min": round((float(end) - float(start)) / 60, 2) if start and end else "",
            "end_reason": r[5] or "open",
            "messages": r[6] or 0,
            "tool_calls": r[7] or 0,
            "api_calls": r[8] or 0,
            "input_tokens": r[9] or 0,
            "output_tokens": r[10] or 0,
            "cache_read_tokens": r[11] or 0,
            "reasoning_tokens": r[12] or 0,
            "est_cost_usd": round(r[13], 5) if r[13] is not None else "",
            "cost_status": r[14] or "unknown",
        })
    write_csv("sessions.csv", sessions, list(sessions[0].keys()))

    # ---- tool calls: timestamp + tool name only, one row per call ----
    calls = []
    for sid, tool_name, ts in cur.execute(
            "select session_id, tool_name, timestamp from messages "
            "where tool_name is not null and tool_name != '' order by timestamp"):
        calls.append({
            "session_key": keys.get(sid, "unmapped"),
            "called_at": iso(ts),
            "tool_name": tool_name,
        })
    write_csv("tool_calls.csv", calls, ["session_key", "called_at", "tool_name"])

    # ---- per-model usage: the raw model strings, unnormalized on purpose ----
    usage = []
    for sid, model, calls_n, in_tok, out_tok, cache_tok, cost, status in cur.execute(
            """select session_id, model, api_call_count, input_tokens, output_tokens,
                      cache_read_tokens, estimated_cost_usd, cost_status
               from session_model_usage"""):
        usage.append({
            "session_key": keys.get(sid, "unmapped"),
            "model_raw": model or "unknown",
            "api_calls": calls_n or 0,
            "input_tokens": in_tok or 0,
            "output_tokens": out_tok or 0,
            "cache_read_tokens": cache_tok or 0,
            "est_cost_usd": round(cost, 5) if cost is not None else "",
            "cost_status": status or "unknown",
        })
    write_csv("model_usage.csv", usage, list(usage[0].keys()))

    # ---- weekly activity: derived from the session table ----
    weeks = {}
    for s in sessions:
        if not s["started_at"]:
            continue
        d = dt.datetime.fromisoformat(s["started_at"])
        wk = d - dt.timedelta(days=d.weekday())
        w = weeks.setdefault(wk.strftime("%Y-%m-%d"), {
            "week_start": wk.strftime("%Y-%m-%d"), "sessions": 0, "days_active": set(),
            "messages": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0.0,
        })
        w["sessions"] += 1
        w["days_active"].add(s["started_at"][:10])
        w["messages"] += s["messages"]
        w["tool_calls"] += s["tool_calls"]
        w["input_tokens"] += s["input_tokens"]
        w["output_tokens"] += s["output_tokens"]
        w["est_cost_usd"] += float(s["est_cost_usd"] or 0)
    weekly = []
    for k in sorted(weeks):
        w = weeks[k]
        weekly.append({
            "week_start": w["week_start"], "sessions": w["sessions"],
            "days_active": len(w["days_active"]), "messages": w["messages"],
            "tool_calls": w["tool_calls"], "input_tokens": w["input_tokens"],
            "output_tokens": w["output_tokens"], "est_cost_usd": round(w["est_cost_usd"], 4),
        })
    write_csv("weekly_activity.csv", weekly, list(weekly[0].keys()))

    # ---- cron executions: date + status counts only, no job identity ----
    if os.path.exists(CRON_DB):
        ccon = sqlite3.connect(f"file:{CRON_DB}?mode=ro", uri=True)
        days = {}
        for status, started in ccon.execute("select status, started_at from executions"):
            day = (iso_any(started) or "")[:10]
            if not day:
                continue
            d = days.setdefault(day, {"day": day, "executions": 0, "completed": 0, "other": 0})
            d["executions"] += 1
            if (status or "").lower() == "completed":
                d["completed"] += 1
            else:
                d["other"] += 1
        rows = [days[k] for k in sorted(days)]
        write_csv("cron_executions.csv", rows, ["day", "executions", "completed", "other"])

    print(f"\nwrote to {OUT}")


if __name__ == "__main__":
    main()
