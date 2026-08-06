# Documentation audit: building a complex flow from the docs alone

**Date:** 2026-08-05/06 · **Auditor:** acting as a mid-level engineer new to Swarm, using only
this docs site plus the `swarm` binary found at `/tmp/swarm-latest` (docs repo @ `7b3e97d`).

**The task I set myself:** build an RFQ vendor-evaluation desk — an RFQ arrives with N vendor
proposals, each vendor gets its own template-flow instance with its own assessor agent
(`memory: true`), results converge through a barrier join, a weighted decision either
auto-awards or parks at a human decision gate with an SLA timer and mailbox escalation, plus a
mock agent and a scenario test. This deliberately exercises the features the docs sell
hardest: composition, fan-out/fan-in, per-instance agents, gates, timers, testing.

**Bundle location:** `scratchpad/rfq-desk/` (plus a minimal `scratchpad/bisect/` repro bundle).

**Outcome in one line:** I got the full bundle to `verify ok`, but I could not run it — and
bisection shows the blocker is that *any agent subscribed inside a template child breaks event
publish at runtime*, a verify-clean, documented pattern. Along the way I logged ~30 friction
points, split below into reading-phase, verify-phase, and runtime-phase.

---

## Phase 1 — Reading the docs (before writing a line)

The concept pages are genuinely good: the two-actor model (nodes own state, agents propose),
producer-complete payloads, and the handler pipeline all landed on first read. Friction was
concentrated in what's *missing*, not what's wrong:

**R1. No install path that works.** `installation.mdx` says "From a clone of the repository:
`go install ./cmd/swarm`" — but never gives the clone URL, and there is no release/download
instruction anywhere. Doc links point at `github.com/division-sh/swarm`; a newcomer has to
infer that. There is no `brew`/`curl` path. (I only proceeded because a binary happened to
exist at `/tmp/swarm-latest`.)

**R2. "One entity per instance" vs. every example.** `flows-and-entities.mdx` states **"Each
instance owns exactly one entity"** as *the* scaling rule. Yet the doc examples repeatedly
show one flow holding many entities keyed by business id: `entity-acquisition.mdx`'s orders
and sessions flows (`create_entity` per order, `select_entity` by `order_id`),
`actions.mdx`'s incident log, and `composition.mdx`'s parent that "holds many orders." Is a
plain (non-template) flow allowed to hold many entities or not? Can the *root* flow? Nothing
answers it. I built the root the way the examples do and it verified — so the bold rule as
stated appears false, or the examples teach an anti-pattern. Either way a reader can't tell.

**R3. The join/fan-in grammar has no reference.** `join:` rows and fan-in resolution pins
(`aggregation`, `window`, `dedup_by`, `singleton`) appear **only** in `build/parallel-work.mdx`.
`reference/handler-fields.mdx` — advertised as "every field a handler can declare" — has no
`join` entry at all. Two fields in the example are never explained anywhere:
- `singleton: scout` — what does the value name? A flow id? An instance? A node?
- `output: payload.match_score` — where does the collected value *go*? (This matters; see V-phase.)

**R4. No documented way to aggregate over join results.** The whole point of my fan-in was
"compute the top score across arrivals." The docs show the join settling and advancing, but
never show the collector *reading* what arrived. `accumulated.*` is scoped to `accumulate`,
`join.output`'s destination is unexplained, and (as I later learned at verify) the join may
not coexist with `data_accumulation`. As far as the docs go, there is no legal way to fold
joined results into entity state. My final contract routes everything to the human gate
because the auto-award branch is unimplementable.

**R5. Small type-system gaps.**
- `types.yaml` shows `[LineItem]` but never a list of scalars (`[text]`) — and never warns
  that unquoted `[text]` is a YAML *flow list*, not a string. I had to guess quoting.
- Zero-field events (`award.approved: {}`) are never shown, though gates force you to need them.
- An event that crosses a flow boundary is declared in both flows' `events.yaml` — must the
  two declarations match? Is drift detected? Undocumented.

**R6. Pin naming/addressing grammar is underspecified.** `connect` addresses are
`<flow-id>.<pin-name>`, but when a pin is declared in the short form
(`outputs: events: [vendor.assessed]`) nothing says what the pin's *name* is. Event names
contain dots, so `.vendor.discovered` visually collides with the "leading dot = root pin"
rule and `evaluation.vendor.assessed` is flow-id + a dotted name. My guesses happened to
compile — but they were guesses, confirmed only by `describe`.

**R7. Reference contradicts guide on `id`/`role`.** `reference/contracts/agents.mdx` marks
`id` and `role` as **required** fields; `build/agents-and-prompts.mdx` says "you usually do
not write `id:` or `role:`" because the map key is both. One of them is wrong (the analyzer
sides with the guide).

**R8. `mock:` is invisible to the reference.** The agent `mock:` field exists only in
`build/testing.mdx`; the agents.yaml reference doesn't list it. Open question a reader can't
answer: does a committed `mock:` disable the real model in production, or only under test?

**R9. Expression gaps.** The CEL page's operator list omits the conditional operator
(`cond ? a : b`), which is the only way to write a running max/min fold. (Verify accepted my
ternaries, so the list is incomplete.)

**R10. No "on stage entry" hook.** Gates and timers attach to stages, but there is no way to
say "when the entity enters this stage, write a mailbox item." I ended up abusing a gate for
the join-timeout notification. A sentence on the idiom (or its absence) would save real time.

---

## Phase 2 — `swarm verify`: where the docs and the analyzer disagree

The analyzer's error format is excellent — named check, file/line, remediation line. But it
enforces a contract the docs don't teach. Every item below is a *doc-vs-analyzer* mismatch I
hit with contracts written faithfully from the docs:

**V1. Child `schema.yaml` requires `name:`.** `invalid_field_detection: flow schema
evaluation missing required field name`. No schema.yaml example in the docs (including the
template-child ones in `parallel-work.mdx` and `patterns/overview.mdx`) shows a `name:` field.

**V2. The documented join grammar is rejected wholesale.** Written per `parallel-work.mdx`
(`members: {from: entity.vendor_ids}`, `window: {from: entity.batch_id}`, optional `output`,
`data_accumulation` alongside), verify raises four blockers:
- `handler.join is an outcome-owning finite barrier and cannot be combined with handler
  fields data_accumulation` — docs never say the join owns the handler exclusively.
- `join.members.by must be a top-level payload.<field> path` — a `by:` key the docs never show.
- `join.window.by must reference a declared top-level text payload field` — same.
- `join.output must be a top-level payload.<field> path` — so `output` is **mandatory**,
  while the docs treat it as an unexplained extra.
The accepted shape (found by error-driven search) is
`members: {by: payload.X, from: entity.Xs}`, `window: {by: payload.W, from: entity.W}`,
`output: payload.Y`, plus `on_complete`/`timeout`. None of this is written anywhere.

**V3. Stage-gate emits may not read the entity.** `stage gate emits support only literals or
exact decision.<field> references`. The docs' gate example only ever emits `decision.*`
fields, but nothing states the restriction — and it has real design consequences: to emit a
business event carrying entity data after an approval, you must add a relay event **and** a
relay stage per outcome (gate → `awarding` → handler enriches from entity → terminal),
because the gate also can't advance straight to terminal without stranding its own emit. My
schema grew two stages and three events solely to satisfy this undocumented rule.

**V4. Gate emits don't count as producers.** With the gate emitting `award.approved`, verify
still raises `event_producer_exists: 'award.approved' subscribed but nobody emits`. The fix —
`swarm: {producer: mailbox_human}` on the event — I found only because the events reference
mentions that value in passing as "exceptional producer proof." Nothing connects gates to it.

**V5. `fan_out.as: item` is a reserved-word collision** (`collides with a reserved expression
root`) — yet `patterns/overview.mdx`'s canonical fan-out example is literally `as: item`.
Copying the pattern page verbatim fails to parse.

**V6. "At least one terminal stage" is mandatory** (`state_machine_coherence`). Reasonable —
but the state-machine page presents terminal stages as a *kind* of stage, never as required.

**V7. Gate `context:` reads don't count as reader coverage.** Fields read only by a gate's
`context:` (e.g. `entity.title`) still produce `entity_reader_coverage` INFO noise.

**V8. Mock module paths resolve from the bundle root**, not the declaring flow's directory.
`testing.mdx` shows `module: mocks/classifier.py` on an agent — in a child flow that exact
line fails verify with a file-not-found against `<bundle-root>/mocks/`.

After fixing V1–V8: **`verify ok`** on the full rfq-desk bundle. Time from first YAML to
green verify: ~9 verify cycles. The error messages carried me; the docs did not.

---

## Phase 3 — Running it: where the docs and the binary disagree

This phase was the roughest. The documented golden path (verify → run/serve → trigger →
trace) required an undocumented workaround at *every* step:

**T1. `swarm run` as documented is retired.** Quickstart and first-flow both say
`swarm run --contracts ./flow --event X --payload p.json`. The binary answers: *"`swarm run`
no longer starts a run. Use `swarm run start ...`"*. The CLI has also grown `doctor`,
`secrets`, `connections`, `bundle`, `forkchat`, `describe`, `migrate-*` — none in
`reference/cli.mdx` as far as the pages I read went, and flag names are inconsistent across
subcommands (`--api-server` on `test`/`event`, `--connect` on `run start`).

**T2. The store-location claims are wrong.** Docs (quickstart, installation, first-flow) say
SQLite lands at `./.swarm/dev.db` and "an empty `.swarm/data/` is auto-created." Actually:
the store goes to `~/.swarm/stores/projects/<name>-<hash>/dev.db`, nothing auto-creates
`.swarm/data`, and `serve`/`run start` **fail to boot** without `--data` ("workspace data
source is required") — a flag the quickstart never mentions.

**T3. Credentials: the documented mechanism doesn't work.**
- `configuration.mdx`: anthropic credential "is checked at the first agent turn" → actually
  checked at **boot**; `serve` refuses to start.
- `installation.mdx`: "Credentials are read from the environment" → exporting
  `ANTHROPIC_API_KEY` did nothing. The only thing that worked was the entirely undocumented
  `swarm secrets set ANTHROPIC_API_KEY`.
- A fully mocked agent does not waive the boot credential — so "zero LLM credentials" testing
  requires you to store a dummy key, which the docs would never tell you.

**T4. The documented `swarm test` loop is unreachable end-to-end.**
- `swarm test --contracts ./flow` (the documented invocation) fails wanting a
  `platform-spec.yaml` in the CWD — despite the quickstart's "the platform spec is embedded
  in the binary." The `--platform-spec` escape hatch is undocumented, and a docs-only user
  has no way to obtain the file (it lives in the source repo they were never told how to clone).
- With a spec: every step fails `BUNDLE_UNAVAILABLE (runtime_context_not_loaded)` — the
  runner needs a *server* with a *registered bundle*. Note the CLI's default port meant my
  first test run silently targeted a different, pre-existing runtime on :8081.
- Registering needs `bundle build` → `bundle register` (both undocumented) — and
  **`bundle build` does not materialize `mocks/`**, so a bundle with a mocked agent cannot be
  built at all. This directly contradicts testing.mdx's "the module is captured at contract
  compilation (path, bytes, digest) into the bundle."
- Net: I never got a scenario to execute. The promised "full agent flow, end to end, with
  zero credentials and zero Docker" is not reachable by any documented or discoverable path.

**T5. `run start`'s embedded runtime can't move its MCP port.** Local-foreground mode
hardcodes MCP on `:8082`; `--mcp-port` is rejected ("not supported until the serve owner can
bind MCP explicitly"). On a machine already running one swarm (as this one was), the
documented one-shot flow cannot start. Workaround: `serve` on custom ports + `run start
--connect`.

**T6. Stale connect snapshots brick a rebooted runtime.** After editing contracts and
restarting `serve` on the same store, every publish fails
`connect route snapshot generation is stale`, permanently. The only fix I found was deleting
the project's store directory under `~/.swarm/stores/`. For a platform whose pitch is
crash-recovery and durable state, "wipe the database after every contract edit" badly needs
documenting (or fixing).

**T7. The flagship finding — a template-child agent breaks publish.** With everything above
worked around, publishing `rfq.submitted` fails:

```
EVENT_PUBLISH_FAILED … preview event route facts: materialize route subscriber:
delivery recipient kind and id are required
```

`verify ok`, `describe` shows a clean topology — the run never starts. I bisected with a
minimal bundle (`scratchpad/bisect/`), adding one documented feature at a time:

| Bundle variant | Result |
|---|---|
| fan_out → template child (nodes only) | ✅ runs, children spawn |
| + return path (child output pin → root input) | ✅ runs |
| + canonical `join:` barrier on the return | ✅ runs; join settles; run completes |
| + **an agent in the child subscribed to the inbound event** | ❌ `delivery recipient kind and id are required` |

So the deterministic machinery — fan-out, per-item instance minting, connect edges, the
barrier join — genuinely works and matches its (post-V2) contract. But the moment a template
child declares an agent subscription, event publish dies with an internal error naming no
contract, no file, and no remediation. **This is the docs' central promise** ("each instance
materializes its own copy of the flow's declared agents… one conversation per vendor") and it
cannot be exercised through any documented path on this binary. A real engineer is hard-stuck
here: nothing in the docs, the analyzer, or the error text offers a next move.

**T8. Small CLI paper cuts.** Bare `swarm event list` returns a raw JSON-RPC error
(`invalid params… field=filter, reason=required parameter is missing`) instead of a usage
message; `event publish` demands `--bundle-hash` with no documented way to learn the server's
canonical hash (`run start` works around it).

---

## What worked well (worth keeping)

- **The analyzer experience.** Named checks with file/line and remediation text made the
  verify loop fast even where the docs were silent — I fixed V1–V8 almost entirely from error
  text. This is the platform's best onboarding surface; the docs should lean on it
  (`analyzer-checks.mdx` was the page I trusted most).
- **The conceptual writing.** Nodes-own/agents-propose, producer-complete payloads, and
  receiver-owned addressing are explained crisply and the model held up exactly as described
  in every agent-less experiment.
- **`swarm describe`** (undocumented!) prints the compiled routing topology with the source
  line of every connect edge — it confirmed my pin-address guesses instantly. It deserves a
  doc page more than half the reference does.
- The fan-out → instance-mint → join round trip really is declarative and race-free in
  practice, exactly as promised — when no agent is involved.

## Top five fixes by engineer-hours saved

1. **Fix or document T7** (template-child agents break publish) — it blocks the product's
   core scenario.
2. **Rewrite the join/fan-in docs to the real grammar** (V2, R3, R4), including where
   `output` lands and the "join owns the handler" rule, with a reference entry in
   handler-fields.
3. **Re-align the CLI docs with the binary** (T1–T5): `run start`, `--data`, `secrets set`,
   real store paths, the test-runner's server/bundle/platform-spec requirements — or better,
   make the binary honor the documented behavior.
4. **Document the gate emit restriction and the relay-stage idiom** (V3, V4) — every
   non-trivial gate hits both within minutes.
5. **Resolve the one-entity-per-instance contradiction** (R2) with an explicit statement
   about plain/root flows, and fix the `as: item` pattern example (V5).

---

*Artifacts (committed next to this file): full flow bundle at `audits/artifacts/rfq-desk/`
(passes `swarm verify`), minimal regression repro at `audits/artifacts/bisect/` (flip: delete
`flows/child/agents.yaml` → runs; restore it → publish fails). My local serve processes were
stopped, the dummy secret removed, and my test stores under `~/.swarm/stores/projects/`
deleted; the pre-existing runtime on :8081 was left untouched.*

---

## Resolution log (2026-08-06, lead — docs @ this commit, platform master `52a9e91a2`)

Ground truth re-established on a fresh master build before resolving; master is unchanged
since the audit, so all findings stood. Every item below is either **fixed in docs** (this
commit) or **filed** against the platform.

**Reading phase**
- R1 → fixed: installation now gives the clone URL and states there are no prebuilt releases.
- R2 → fixed with the precise rule: root/plain flows may hold many entities (the classic
  examples are legal); *static children* may not create per-event entities (boundary
  validation); template = one entity per instance. flows-and-entities and composition updated.
- R3 → fixed: `join` now has a reference entry in handler-fields with the real shape.
- R4 → dissolved: the typed `join.*` context (`expected/completed/missing/results/timed_out`)
  is readable in outcome expressions, and outcomes accept `data_accumulation` — aggregation
  over arrivals is `join.results.max()` in `on_complete`. Documented in parallel-work.
- R5 → fixed: zero-field events, quoted scalar-list types, and the cross-flow
  declaration-agreement rule (drift verified to fail as `key_types_incompatible`) documented.
- R6 → fixed: short-form pin name = the event name; addressing rule spelled out.
- R7 → fixed: agents reference now marks `id`/`role` derived from the map key.
- R8 → fixed: `mock:` documented in the agents reference (bundle-root path, test-only
  execution, boot-credential caveat → #2172).
- R9 → fixed: ternary added to the expressions page.
- R10 → fixed: documented that there is no on-entry hook; the entering transition's handler
  and stage timers are the idiom.

**Verify phase**
- V1 → fixed: child schema examples carry `name:`.
- V2 → fixed: parallel-work teaches the accepted grammar (`members/window {by, from}`,
  mandatory `output` and `timeout`, exclusive handler ownership, outcomes own the writes).
- V3/V4 → fixed: gate-emit restriction (literals + `decision.*`), the relay-stage idiom, and
  `swarm: {producer: mailbox_human}` documented in human-in-the-loop.
- V5 → fixed: `as: item` replaced (`item` documented as reserved) in the pattern examples.
- V6 → fixed: at-least-one-terminal-stage documented as required.
- V7 → filed: #2173 (gate `context:` reads should count as reader coverage).
- V8 → fixed: mock module paths documented as bundle-root-relative.

**Runtime phase**
- T1 → fixed: every invocation now uses `swarm run start`; CLI page aligned.
- T2 → fixed: real store location (`~/.swarm/stores/projects/<name>-<hash>/`) and the
  mandatory `--data` documented in quickstart/installation/first-flow/running-the-runtime.
- T3 → fixed in docs (`swarm secrets set`, boot-time validation) + filed #2172 (mocked
  bundles should waive the boot credential).
- T4 → filed #2170 (bundle build does not materialize `mocks/`; embedded-spec default for
  `swarm test`) + docs now describe the real serve+register loop with honest caveats.
- T5 → filed in #2173 (MCP port pinned; `--mcp-port` rejected) + workaround documented
  (serve on free ports + `run start --connect`). Reproduced independently during resolution.
- T6 → filed #2171 (stale connect snapshot bricks store after contract edit) + a Warning
  with the workaround added to running-the-runtime.
- T7 → filed **#2169 (P0)** with the bisect bundle as the regression fixture; cross-linked
  to #2167/#2161/#2144 and nominated for the #2168 golden-bundle assertions. Docs unchanged
  (the documented pattern is correct; the binary is wrong).
- T8 → filed in #2173.

**Kept:** the audit's "what worked well" list is being acted on too — `swarm describe` gets a
docs page in the next pass, and the analyzer-first onboarding observation is noted for the
docs' structure.
