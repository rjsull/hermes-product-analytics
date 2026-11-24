# Metrics layer specification

Every metric below is either additive, derived, or a snapshot. Mixing those shapes is the most common way a trustworthy pipeline produces a wrong number, so each definition states its shape and its failure mode.

## The three shapes

| shape | examples | rule | what breaks it |
| --- | --- | --- | --- |
| Additive | sessions, messages, tool calls, tokens, cost | sum freely across any dimension and period | double counting when two surfaces report the same session |
| Derived ratio | completion rate, error rate, cost per session, tokens per tool call | compute once per declared period, never average a ratio across periods | averaging weekly ratios into a "quarterly" ratio without weighting |
| Snapshot level | sessions still open, active installs, subscribers, memory entries | as-of values; compare across periods, never sum them | summing daily snapshot rows into a "total" |

A useful test: if a metric's unit changes when you add a time dimension, it is not additive. If it moves when nothing moved, its denominator changed.

## Core definitions

| metric | definition | shape | denominator | trap |
| --- | --- | --- | --- | --- |
| Completion rate | sessions with `session.ended.reason = completed` in period | ratio | sessions started in the same period | counting reaped or open sessions as completions. In my own data this is 48%, not 100% |
| Activation | first-ever session that reaches a `tool.completed` | ratio | new user_keys in period | defining activation as a first session. My tool calls per session went from 0 to 35 while session counts stayed flat |
| Engaged session | session with at least one `tool.completed` | ratio | sessions started in period | counting any session as engaged |
| Weekly active | distinct user_keys with a session in the ISO week | count | not applicable | monthly actives hiding a four-week gap, which is exactly what happened in my own data |
| Retention W1 to W4 | share of a signup-week cohort with any session in week N | ratio | the cohort, named and versioned | recomputing the cohort each period, which rewrites history every month |
| Tool failure rate | `tool.completed` with outcome in (error, timeout) | ratio | all `tool.completed` in period | mixing denied with error. A permission denial is a design signal, an error is a defect |
| Cost per session | sum of estimated cost divided by sessions | ratio | sessions started in period | mixing rows with known and unknown cost status inside one total |
| Tool adoption | distinct `tool_name` per user_key per week | count | not applicable | depth and breadth in one number |

## Denominators and cohorts

Every ratio gets a named cohort as its denominator, and that cohort is versioned the way a dimension is versioned. When a new data source arrives, coverage changes the denominator, not just the numerator: if one source covers 60% of users and another covers 20%, the union is a different population than last period, and a flat engagement rate will appear to move when nothing moved.

Rules:

1. The denominator is named in the metric definition, not chosen at query time.
2. Cohort membership is stored with an `assigned_at` date and never overwritten.
3. A metric whose cohort version changed is not comparable to its own history without a note.
4. Any ratio published without its denominator coverage is not published.

## Which numbers may be combined

When outcome data arrives from systems that observe the world past the click, the join between exposure and outcome produces attribution, and attribution is a claim about evidence. Every outcome fact carries `attribution_confidence`, one of:

| rung | meaning |
| --- | --- |
| measured | exposure and outcome observed in the same system, deterministic key match |
| linked | deterministic join on a shared identifier passed by both sides |
| inferred | probabilistic match, or a redirect or campaign parameter path |
| purchased | third party identity graph |
| assumed | no link at all |

The rule is that rungs are never blended inside a single number. "This program drove 400 enrollments" is only defensible with a stated rung, and a dashboard that adds a measured rung to an assumed rung has produced a number nobody can defend.

## Gating a new data source

Before the first row lands, seven questions get written answers:

1. Key. What joins it to the spine?
2. Grain. One row per what?
3. Clock and restatement policy. When is a row final, and what changes it later?
4. Role. Fact, dimension, or identity service?
5. Coverage base. Who is missing from this source, and by how much?
6. Sensitivity class and legal basis. Where may these rows live and who may see them?
7. Confidence rung. Which rung does it produce?

A source that cannot answer 1 and 2 does not get ingested. A source that cannot answer 5 does not get aggregated.

## Tests that belong in the pipeline

1. No ratio is averaged across periods; ratios are recomputed from additive components.
2. No snapshot metric is summed across periods.
3. Every published ratio names a cohort and its coverage.
4. Reconciling an aggregate against its source table returns zero difference.
5. A model or tool identifier that is not in the registry fails the build, which is the test that would have caught 9 strings mapping to 7 real models in my own data.
6. Every `*.started` event without a terminal event older than the timeout is visible as a defect count, not silently dropped.
