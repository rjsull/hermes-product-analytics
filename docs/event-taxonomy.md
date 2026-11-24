# Proposed event taxonomy: Hermes Agent

A taxonomy is a contract. If two teams can name the same user action two ways, every metric downstream is ambiguous, and the ambiguity always resolves in favor of whichever number is larger. This is the contract I would write, based on measuring my own usage of the product.

## Naming and envelope

Event names are `object.action`, lowercase, past tense at the moment the event fires. The name describes what happened, not what the user did to the interface. No version numbers in names; versioning lives in `schema_version`.

Every event carries this envelope, without exception:

| property | why it exists | notes |
| --- | --- | --- |
| `event_id` | dedupe at ingest | uuid, client or server generated |
| `occurred_at` | the only timestamp used in metrics | server clock, UTC, ISO 8601 |
| `received_at` | clock skew and backfill detection | set on arrival |
| `surface` | segments everything | enum: desktop_app, local_cli, messaging_gateway, scheduled_job, api |
| `app_version` | behavior changes by release | semver of the emitting build |
| `session_key` | join key for a run | one per session |
| `user_key` | the spine | stable across surfaces and devices |
| `consent_state` | gates what may be collected | enum: granted, limited, denied |
| `schema_version` | parse safety | integer per event name |

The envelope is not optional and it is not per-team. The moment one surface omits `surface`, every cross-surface comparison becomes a guess.

## Core events

| event | purpose | required properties | powers |
| --- | --- | --- | --- |
| `session.started` | session beginning | `trigger` (interactive, scheduled, api), `is_first_ever` | activation, session counts, retention cohorts |
| `session.ended` | session terminal state | `reason` (completed, abandoned, error, reaped, timeout), `duration_ms`, `message_count`, `tool_call_count` | completion rate, session quality, churn signals |
| `message.submitted` | user turn accepted | `char_count`, `attachment_count` | engagement, funnel from start to first tool call |
| `message.completed` | assistant turn finished | `model_key`, `latency_ms`, `input_tokens`, `output_tokens`, `finish_reason` | latency, cost, error rates |
| `model.routed` | model selection decision | `model_key`, `route_reason`, `fallback_from` | model mix, cost by route, fallback frequency |
| `tool.called` | tool invocation started | `tool_name`, `surface` | tool mix, adoption depth |
| `tool.completed` | tool invocation resolved | `tool_name`, `outcome` (ok, error, denied, timeout), `duration_ms` | failure rates, retry pressure, permission friction |
| `context.compressed` | context window managed | `tokens_before`, `tokens_after`, `trigger` | cost drivers, quality risk after compression |
| `memory.written` | durable fact stored | `kind`, `source` | memory adoption, trust |
| `skill.loaded` | skill used in a session | `skill_name` | skill adoption per cohort |
| `cron.fired` | scheduled job triggered | `job_key`, `schedule_kind` | scheduled surface share, trigger attribution |
| `cron.completed` | scheduled job resolved | `job_key`, `outcome`, `delivery_outcome` | reliability, silent failure detection |
| `onboarding.completed` | first-run setup finished | `steps_completed` | activation funnel |
| `update.installed` | version change | `from_version`, `to_version` | cohort breaks, regression detection |

## Rules that keep the taxonomy honest

1. **Server timestamps only.** Client clocks skew, and one user's laptop with a wrong timezone will silently move rows across period boundaries.
2. **No free text in properties.** Free text is where personal data leaks into an analytics store, and it destroys cardinality control. If a value matters enough to analyze, it gets an enum.
3. **Property allowlist per event.** An event's schema is closed. New properties are a schema change with a review, not a client-side addition.
4. **Cardinality budget.** No property may exceed 10,000 distinct values per month without a documented reason. High-cardinality ids belong in joins, not in event properties.
5. **`tool_name` and `model_key` come from a registry**, never from a raw client string. My own local data proves the failure mode: the same model recorded under 9 different strings and 7 real identities.
6. **Every event names who is missing.** A per-surface coverage note, because events from a CLI cannot see desktop sessions and a client-side event cannot fire for someone offline.
7. **Terminal state is mandatory.** Any `*.started` event needs a matching terminal event, or a declared timeout after which the row counts as abandoned. Without this, session counts drift upward forever as orphans accumulate.

## What this taxonomy deliberately does not do

No page views, no click streams, no scroll depth, no screen coordinates. Those measure an interface, and the product's value is measured in sessions that accomplished something. The events above are chosen so that a funnel can be built from session start to a real tool completion, and nothing in the taxonomy exists to make a dashboard look busy.
