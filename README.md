# Inside a product, from the analytics seat

I use Hermes Agent every day. I also build measurement systems for a living. This repo is what happens when those two things meet: a proposed event taxonomy for Hermes Agent, the metrics layer I would build on top of it, and an analysis of my own 90 sessions read out of the local store.

It is not an audit of anyone's product. It is work on real data, with the privacy choices stated up front and reproducible from the scripts in this repo.

## Snapshot (frozen 2026-11-24)

| metric | value |
| --- | --- |
| Window | 2026-07-28 to 2026-11-24, 18 calendar weeks, 12 with activity |
| Sessions | 90 |
| Sessions that ended cleanly | 43 (48%) |
| Sessions reaped as orphans | 25 |
| Sessions with no output | 6 |
| Messages | 2,209 |
| Tool calls | 956 (10.6 per session) |
| Input / output tokens | 6.05M / 723K (8.4 to 1) |
| Estimated cost | $1.98 ($0.022 per session) |
| Surfaces | scheduled 64, local CLI 15, desktop 10, messaging gateway 1 |

The source database is live, so counts move as I use the product. The CSVs in `data/` are the frozen snapshot everything below is computed from.

## Five things the data said

### 1. Half the sessions never ended on purpose

43 of 90 sessions finished cleanly. 25 were reaped as orphans, 13 at startup and 12 from the workspace. Six more ended with no output at all, and 16 have no terminal state yet. Counting rows in the session table as "usage" inflates the number by roughly 2x.

**Fix in the taxonomy:** `session.ended` carries a required `reason` enum. Sessions without a terminal event are counted as open, and open sessions never appear in a completion numerator.

### 2. This is a scheduled product as much as an interactive one

64 of 90 sessions (71%) were triggered by a schedule. Interactive use accounts for 26 sessions across CLI, desktop, and one messaging gateway. Any engagement definition written for interactive use would ignore most of the traffic, and any cost definition written for interactive use would misprice it.

**Fix:** `surface` is a required property on every event and a first-class dimension on every metric.

### 3. Tool intensity moved. Session counts did not.

The weeks of 09-21 and 09-28 produced 8 sessions and zero tool calls. The week of 11-16 produced 13 sessions and 449 tool calls, 47% of all tool calls in the window. Sessions per week stayed between 5 and 13 the whole time, so a session-count chart shows a flat line while the product was being used in a completely different way.

**Fix:** `tool.called` per session is a quality metric for activation, not a volume metric. Activation is defined as a first session that reaches a tool call, not a first session.

### 4. Model identity is split by routing detail

The data holds 9 distinct model strings and 7 actual models. GLM traffic reads as 728 API calls only after normalization; as stored it is 603 under one provider prefix plus 125 under another. DeepSeek splits the same way, 134 plus 89. The differences are serving route and region suffix, not behavior. Every per-model cost, latency, or quality comparison built on the raw strings is wrong by construction.

**Fix:** a normalized `model_key` in the semantic layer, the raw string retained beside it for debugging, and a test that fails when an unmapped routing variant appears in the data.

### 5. Cost is an estimate with known holes, so it needs a stated denominator

$1.98 estimated across the window, $0.022 per session, at an 8.4 to 1 input to output token ratio. Some rows carry no cost status at all, which means a per-model cost chart silently mixes estimated rows with unknown ones. Cost per session and cost per tool call are honest denominators. A total labeled "spend" is not.

**Fix:** `cost_status` rides on every cost fact and unknown never co-mingles inside a total. The 8.4 to 1 ratio also says the cost problem is context management, not output length.

**And the retention reality:** 12 active weeks out of 18, with a four-week gap in August and a two-week gap in October. Week-level cohorts show that shape. Monthly active users would hide it entirely.

## What is in the repo

```
extract.py        read the local store, write aggregate CSVs (excludes PII by construction)
analyze.py        normalize model ids, compute metrics, emit charts (stdlib only)
pii_scan.py       pre-commit scan for contact data, ids, paths, secrets
data/             frozen CSVs plus metrics.json
charts/           SVG charts, one per finding
docs/event-taxonomy.md    proposed events, properties, identity, sensitivity
docs/metrics-layer.md     metric definitions, shapes, denominators, gating
```

## Privacy, by construction

The extraction script never reads or writes message content, session titles, session keys, chat or channel ids, display names, user ids, working directory, system prompts, tool-name hashes, cron job names, cron job ids, or cron job prompts. Session identifiers are replaced with sequential pseudonyms ordered by start time, so rows stay joinable inside this repo and meaningless outside it. The gateway surface is labeled generically because naming it would put a personal communication channel into a public repo for no analytical gain.

`pii_scan.py` runs before every commit. It is in the repo so the check is inspectable, and it reports clean:

```
$ python3 pii_scan.py
PII/secret scan: clean
```

## Method and limits

This is derived from local state, not from instrumented events. One user, one machine, 18 weeks, and sessions are not users. There is no cross-device identity, no consent gating, no experiment, and cost is an estimate. Everything here describes one person's usage, which is enough to find definition bugs and not enough to generalize to a user base.

If I were instrumenting Hermes Agent, this is the order I would add events, and the reason:

1. `session.ended` with a reason enum, which closes the largest hole in this dataset.
2. `tool.completed` with an outcome, so tool failure rates are countable rather than inferred from message roles.
3. Activation as a first tool call, which turns finding 3 into a cohort you can measure.
4. `context.compressed`, because an 8.4 to 1 token ratio makes compression a cost driver.
5. `cron.fired` with outcome, because 71% of the traffic is scheduled and none of it is currently attributable to a trigger.

## Reproduce

```
python3 extract.py     # reads ~/.hermes/state.db read-only
python3 analyze.py     # writes data/metrics.json and charts/*.svg
python3 pii_scan.py    # must print clean before any commit
```

Python 3 standard library only. No dependencies, no network, no credentials.

Ryan J. Sullivan
