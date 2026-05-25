# Learning Swarm — A Student Engineer's Journal

I'm a regular software engineer who has never seen Swarm before. I'm reading the
docs in the order the site presents them (Guides → Reference → API). I'll record:

- **Got it** — what landed clearly
- **Confused** — where I stumbled, what was missing, what I had to infer
- **Questions** — things the docs left me wanting to know
- **Doc gaps** — concrete suggestions for the doc team

Goal: judge whether a normal engineer can actually pick up the system from these docs.

---

## Reading order (Guides tab)
1. index → why-swarm → quickstart → installation
2. Core concepts (overview, flows-and-entities, system-nodes-and-handlers,
   agents-and-sessions, events-and-routing, gates-timers-and-state, expressions,
   persistence-replay-and-fork, human-in-the-loop)
3. Build a flow
4. Handlers
5. Patterns
6. Operating Swarm
7. (then Reference + API as needed)

---

## Block 1 — Getting Started (index, why-swarm, quickstart, installation)

### Got it
- The one-sentence thesis lands immediately: **"the LLM does not run the system."**
  Agents reason in small scoped tasks; a deterministic engine owns state, routing, rules.
  This is the clearest framing I've seen for "why not just CrewAI/AutoGen."
- Three actors, cleanly separated: **system nodes** (deterministic code), **agents**
  (LLM sessions that emit but never write state), **humans** (durable mailbox). Good.
- "One transaction per transition" + "every event persisted → replay/fork" is repeated
  enough that it sticks.
- `why-swarm` is genuinely excellent: the strong-fit / weak-fit lists and the comparison
  table (vs CrewAI/AutoGen/LangGraph) tell me *when* to reach for this. Positioning Swarm
  near Temporal/Restate/Inngest ("durable execution for LLMs") is the aha moment.
- Quickstart is honest that the LLM credential is validated at boot even though the demo
  flow has no agents. Good expectation-setting.

### Confused / friction
- **`swarm run` vs `swarm serve`** — Quickstart uses `swarm run` ("boots a runtime in
  process"); Installation uses `swarm serve` ("the runtime, API, health, MCP startup
  owner"). A newcomer can't tell if `run` is a dev convenience that wraps `serve`, or a
  separate thing. The relationship is never stated where I first hit it. **First real gap.**
- **Port 8070 vs 8081** — Installation flags that Compose overrides 8081→8070. It's
  *acknowledged* but the "why" is hand-wavy ("Compose overrides the port"). Minor, but a
  reader wiring up CLI `--api-server` could trip here.
- **The five files appear before the model.** Quickstart shows package/schema/events/
  nodes/agents with fields like `pins.inputs.events`, `create_entity`, `advances_to` —
  intuitive enough to follow, but I'm taking them on faith. That's the right call for a
  quickstart *as long as* concepts/build pages actually close the loop. Flagging to verify.
- The empty `agents.yaml: {}` with the note "a flow must declare either agents or child
  flows" — small but memorable rule. I'll watch for where this is formally specified.

### Questions I'm carrying forward
- Is `swarm run` ephemeral (throwaway DB state?) or does it persist like `serve`?
- What exactly is an "entity"? Quickstart says the node "creates an entity" — I'm
  inferring it's an instance of the flow's state machine. Need concepts to confirm.
- What's a "pin"? Shown as `pins.inputs.events` but not defined yet.

---

## Block 2 — Core Concepts

### Got it (this section is the strongest part of the docs so far)
- **`concepts/overview`** resolved both my carried questions in one page: the **nouns
  table** (flow/instance/entity/state/node/agent/handler/event/gate/timer/pin) and the
  "runtime in six sentences" are exactly the scaffolding I wanted. An *entity* = a mutable
  document (state + gates + fields) moving through a flow instance. A *pin* = a flow's
  typed public input/output. Confirmed my inferences.
- The handler pipeline is taught twice, well: overview gives the stage diagram
  (Acquire→Evaluate→Branch→Apply→Emit→Action), and `system-nodes-and-handlers` reframes it
  in plain English ("if you've written a web route handler, this is the same idea"). The
  **"you declare what, the engine decides when"** point (YAML order doesn't matter; fixed
  execution order) is important and clearly made.
- **`events-and-routing`** is excellent. "Events are the only way work moves," the 4-step
  lifecycle (validate→persist→resolve→deliver, persist-before-deliver enabling replay),
  **"producer-complete"** (emitter fills every payload field, nothing auto-copied), and
  **"routing is derived, not chosen"** all land. The "nodes own, agents observe" +
  **"dual delivery"** table makes the at-most-one-node / many-agents rule click.
- `persistence-replay-and-fork`: the two layers (event store = *what happened*, mutation
  log = *what changed and why*) and the **flight recorder** (4 tables joined on `run_id`)
  are a genuinely good mental model for the audit story.
- `human-in-the-loop`: **"autonomy is a dial, not a switch"** — a handler is autonomous
  unless it adds a `mailbox_write`. Crisp. The decision-sheet idea is intuitive.

### Confused / friction
- **`agents-and-sessions` overloads the newcomer AND has a forward-reference problem.**
  It's the 4th concept page, but it leans hard on a **root flow vs child flow** distinction
  that hasn't been introduced yet: "`session_per_entity` … requires the agent to be
  declared inside a flow, that is, a child flow," and "a single root flow uses
  `conversation_mode: task`." As a reader going in order, I don't yet know what makes a
  flow "root" vs "child" — that's in `build/composition`, much later. I had to just accept
  the rule. **This is the biggest sequencing gap I've hit.** Either (a) introduce
  root/child briefly here, or (b) move the root/child constraints to a callout that links
  forward, or (c) reorder so a composition primer precedes agent session scope.
- `conversation_mode` × `session_scope` is a 4×3-ish matrix dropped at once (task/session/
  session_per_entity/stateless × global/flow/entity) with cross-cutting "must match" rules.
  It's correct and even well-written, but it's a lot for a first pass. A small **valid
  combinations table** would beat three prose bullets + two extra rules.
- `gates-timers-and-state`: "Gates are projected by **`flow_scope_key`**, so they stay
  stable across instance ids." — `flow_scope_key` is unexplained jargon here; first and
  only mention in concepts. A newcomer can't parse what this guarantees. Either define it
  inline or link to where it's defined.
- Still **unresolved: `swarm run` vs `swarm serve`.** Concepts didn't touch CLI (fair),
  but the question persists into Build.

### New questions
- Is an agent "session" the same thing the API calls a "conversation"? (API has
  `conversation.*` endpoints.) The vocabulary may be split.
- The fork `<Note>` honestly says the operator command surface is "in progress" — good
  honesty, but as a newcomer evaluating the tool I now wonder how much of "replay/fork"
  (a headline feature) is actually usable today vs. plumbing-only.

---

## Block 3 — Build a flow

### Got it
- `flow-package` is a perfect orientation: the directory layout, the one-line "what each
  file does" table, and the mermaid showing events→nodes/agents→entities/schema. The
  "minimum package = package.yaml + schema.yaml" + "must have agents.yaml or a child flow"
  rule finally formally states the thing quickstart hinted at. Loop closed.
- **`first-flow` is the best page on the site.** It builds the support-ticket flow file by
  file, each step explains *why*, and it ends with an **annotated trace of a real run**
  mapped back to the four core ideas. By the end I could read a handler as a sentence. The
  "what the contracts buy you" section is the why-swarm argument made concrete on code I
  just wrote — very persuasive.
- `state-machine`, `agents-and-prompts`, `tools`, `policy` are all tight reference-style
  pages. The `native_tools` vs `tools` vs `permissions` three-way distinction in `tools`
  is explained unusually well ("native_tools = what it does on the host; permissions = what
  it does to shared platform state"). Prompt `{{variable}}` substitution priority order is
  spelled out. Policy inheritance (child→parent→root) with the mermaid is clear.
- **`composition` is where root/child finally clicks.** "Why crossing a boundary needs a
  target" (a flow isn't a single recipient → which entity, in which instance?) is a great
  framing, and the orders/fulfillment round-trip (`create_flow_instance` + `config_from`
  → child works → output pin + parent route → `select_entity` re-attach) is complete and
  followable. Static-vs-template table is clear.

### Confused / friction
- **`testing` is the weakest Build page — conceptual, not operational.** It names three
  layers (analyzer / test packages / agent fixtures) and shows an `expected.yaml`, but:
  - It never shows the **command** to run a test package. `swarm verify` is for static
    checks; how do I actually execute the trigger and assert the `expected.yaml`? No
    `swarm test` shown here.
  - Agent fixtures: "run agents in a scripted mode and supply fixture responses" — but no
    file format, no directory convention, no command. I cannot write a fixture from this
    page. **Real gap for anyone trying to test their flow.**
- **The forward-reference debt from Blocks 1–2 is all paid in `composition` (Build page 6).**
  That's late: the root/child constraint bit me in concepts/agents-and-sessions (a *concept*
  page) and again in first-flow's Note. The info is good; it just arrives well after the
  first time a reader needs it.
- **Trace discrepancy in `first-flow`:** every orchestrator line shows
  `subscriber=node/__runtime_replay_scope__`, but the prose says "the orchestrator (the one
  system node) handles it." A newcomer will ask "why is my `ticket-orchestrator` node
  showing up as `__runtime_replay_scope__`?" Either the trace is from an internal build with
  a leaky scope name, or it needs a one-line explanation. As-is it undercuts the otherwise
  excellent annotated-trace section.

## Block 4 — Handlers (the deep dive)

### Got it
- The seven sub-pages line up 1:1 with the pipeline stages, so the structure teaches the
  execution order by itself. Each page is short and example-first.
- `entity-acquisition`: the three modes are clear, and the **two complete `swarm verify`-
  passing flows** (orders lifecycle; per-session counter) are exactly the kind of
  copy-pasteable proof a working engineer wants. "create on first event, select on the rest"
  is the pattern I'll reach for.
- `guards`: `on_fail` table (reject/discard/kill/escalate) is crisp; "guard reads entity
  *before* this handler's writes" is the kind of ordering detail that prevents real bugs.
- `data-and-state`: the four `writes` forms (direct/mapped/literal/computed) on one example
  is the clearest possible presentation. "value not literal", "value and expression are
  mutually exclusive" — good landmine-flagging.
- `emitting`: producer-complete restated; bare-string-emit = empty payload gotcha is
  well-flagged ("analyzer accepts it; the empty payload only shows up at runtime").
- `branching`: **rules (dispatch on incoming payload) vs on_complete (decide after
  computing)** is a genuinely clarifying split, and "`accumulated.*` is readable in
  on_complete but not rules" explains *why* they're different, not just that they are.
- `accumulation`: dense but every operator has an example; the `dedup_by` defaults-to-sender
  gotcha is exactly the sort of thing that would silently eat events, and it's called out.
- `actions`: each of the four actions ships a full minimal flow. The `record_evidence` vs
  `data_accumulation` Note (append-only log vs overwriting fields) preempts a real confusion.

### Confused / friction
- **`gate_state` appears unexplained.** `data-and-state` says "Declare the gate in the
  node's `gate_state`" but never shows a `gate_state` block. Combined with the concept
  page's `flow_scope_key` (also unexplained) and `sets_gate`/`clear_gates`/
  `entity.gates.<name>`, the gate mechanism is scattered across pages with no single place
  that shows the full declaration. A worked gate example (declare in `gate_state`, set it,
  guard on it, clear it) would consolidate this.
- `accumulation` leans on the reference (`/reference/accumulation`) for the important rules
  (`materialize_from` projection, completion semantics). Reasonable for a build page, but it
  means you can't fully use `accumulate` from this page alone.

---

## Block 5 — Patterns

### Got it
- A solid cookbook: guard-with-escalation, multi-gate pipeline, accumulate+compute, fan-out,
  rules routing, dynamic instances, timers, cross-entity queries, payload transform,
  independent reviewers. Each is a copy-paste starting point. Good "recipes" complement to
  the reference-style handler pages.

### Confused / friction
- **`store_as` inconsistency across pages.** In `accumulation.mdx`, compute uses
  `store_as: entity.composite` (entity-prefixed) and filter uses `store_as: entity.passing`.
  In `patterns/overview`, the same compute uses `store_as: composite_score` (bare, no
  prefix). A copy-paster can't tell whether `store_as` wants `entity.X` or `X`. One of these
  is wrong, or both are valid and that should be stated. **Concrete doc bug to reconcile.**
- **`query` shape inconsistency.** `accumulation.mdx` shows `query:` as a single map;
  `patterns/overview` shows `query:` as a list of query objects. Both may be valid, but a
  newcomer sees two shapes for the same field with no note that both work.
- Only one page in the Patterns group. Fine as a cookbook, but the nav "group" of one feels
  thin; could fold in more real-world shapes (sagas, compensation, human-gated approval end
  to end).

## Block 6 — Operating Swarm

### Got it
- **`running-the-runtime` finally answers my Block-1 question:** "For one-shot local runs,
  `swarm run` boots a runtime in-process; `swarm serve` is the long-running runtime." Clear
  — but this lands ~25 pages after quickstart/installation where the confusion starts. A
  one-line cross-reference up front would erase the whole problem.
- The **run lifecycle** section is genuinely valuable: running/completed/failed/paused/
  stalled, and the crucial truth that **"a failed handler or agent does NOT fail the run —
  it dead-letters and the run continues; a run can reach `completed` with dead letters
  inside it. Watch dead letters separately."** That's a production gotcha stated plainly.
- "Entity state is scoped to the current run" — important, and flagged where it matters.
- `pause --all` gates *new* ingress vs `pause <run-id>` vs `stop --all` (one run at a time,
  asks confirmation) — the asymmetry is spelled out, which prevents a dangerous mistake.
- `reliability` is excellent and complete: retry table (handler 3× backoff; agent 1× then
  dead-letter), dead-letter `failure_type` catalog, chain-depth cap of 50 (and that overflow
  is an emission interception, not a handler failure). This is the kind of bounded-behavior
  detail that earns trust.
- `deployment` is honest about scope: "single deployment; distributed execution and
  multi-tenant isolation are not yet in scope." Good to know before I build on it.

### Confused / friction
- **`budget-and-cost`: percentages of WHAT?** `budget_warning_percent: 60`,
  `budget_throttle_percent: 80`, `budget_emergency_percent: 95` — but the page never says
  where the *absolute* budget/limit (the denominator) is configured. 60% of what? Per run?
  Per entity? Per day? A dollar cap? A token cap? This is a real hole: I can set thresholds
  but can't find where the budget they're a percentage of is defined. **Top operational gap.**
- `fork-and-replay` repeats the concept-page caveat that run-level fork is plumbing-only
  ("operator command surface is in progress"). Consistent and honest, but it confirms that
  one of the six headline "Design positions" on the landing page (replayable *and forkable*)
  is only half-shipped at the operator level. Worth a clearer "what works today" line on the
  landing/why pages so expectations are set before page 30.

---

## Block 7 — Reference + API (spot-checks to verify my flagged gaps)

I didn't read every reference page; I used them to confirm/deny the gaps I'd flagged.

### Confirmed by checking the reference
- **`reference/cli` has NO `swarm test`.** I read the full command list: serve, run, verify,
  version, completion, then runs/events/entities/agents/control. Nothing runs a *test
  package* or an *agent fixture*. So `build/testing`'s middle and bottom layers are
  documented capabilities with **no documented way to invoke them**. (The page even notes
  `swarm fork` is intentionally absent — but says nothing about how to run the tests it
  describes.) This is now my #2 gap.
- **`reference/configuration` does not define the budget denominator either.** Combined with
  a full-repo grep (`budget_limit`, `cost_limit`, `token_budget`, `max_budget`, "percent of"
  — all zero hits), I'm confident: the budget *percentages* have no documented absolute cap
  anywhere. #1 gap stands and is verified, not just unnoticed by me.
- **`gate_state`** is defined in `reference/contracts/nodes` as literally "Gate field
  definitions." — no shape, no example. So the gate mechanism (`gate_state` declare +
  `sets_gate` + `entity.gates.x` guard + `clear_gates`) is never shown end-to-end anywhere.

### Corrected (being fair to the docs)
- **`flow_scope_key` IS defined** — in the glossary as "Flow scope key" ("a flow's semantic
  namespace by position in the tree, stable across instances"). My earlier "never defined"
  was wrong; my grep missed it because the glossary uses spaces, not snake_case. The *real*
  (smaller) issue: the gates concept page uses the snake_case identifier without linking to
  that glossary entry, so the definition and the usage never meet.
- **session vs conversation**: the glossary defines *Session* (not *Conversation*), but the
  API overview clears it up — `conversation.*` is "Sessions, turns, and transcripts." So a
  conversation is the API's name for a session's record. Reasonable, just not stated in the
  glossary.

### New finding while in the API tab
- **OpenRPC vs OpenAPI mismatch.** `api-reference/introduction` says the reference is
  "generated from the OpenRPC source of truth (`openrpc.json`)", but the shipped artifact is
  `api-reference/openapi.json` and `docs.json` points to `openapi.json`. There is no
  `openrpc.json` in the repo. Either the prose or the artifact name is stale. Small, but it's
  exactly the sentence that tells a reader where the real source of truth lives.

### The API tab is, otherwise, excellent
- One JSON-RPC 2.0 surface; the per-method "POST /v1/rpc/<method>" paths are flagged as a
  docs convenience. Auth/envelope/pagination/idempotency are all concrete (error
  discriminator is `data.code`, idempotency keyed by `(method, token, key)` for 24h, cursor
  pagination only). The **"Not in v1"** section (no multi-tenancy, no rate limiting, no
  batch) and the WebSocket "token checked once at upgrade" caveat set expectations honestly.
  Subscriptions page is clear that delivery is eventual/lossy and you reconcile via the
  matching `list` + `replay_since`.

---

# Final assessment — can a regular engineer learn Swarm from these docs?

**Short answer: yes, comfortably.** I started knowing nothing about Swarm and finished able
to (a) explain the core thesis, (b) hand-write and mentally `verify` a multi-agent flow,
(c) read a run trace, and (d) operate it (trace, mailbox, pause, dead letters). The
information architecture (Getting Started → Concepts → Build → Handlers → Patterns →
Operate, then Reference/API) matches how an engineer actually onboards, and the writing is
unusually disciplined: every page leads with *why*, names its gotchas, and stays in plain
English. `why-swarm` and `build/first-flow` are standout pages.

**What the docs do better than most:** the determinism thesis is repeated until it sticks;
nearly every handler concept ships a complete `swarm verify`-passing flow; the operational
truths that bite people in production (failed handler ≠ failed run; dead letters; chain
depth 50; pause asymmetry; entity state scoped to a run) are stated plainly; and the docs
are honest about what is *not* shipped (run-fork, multi-tenancy, rate limiting).

### Prioritized gaps for the doc team (verified, most → least impactful)

1. **Budget: define the denominator.** `budget_*_percent` keys are percentages of an
   absolute budget that is documented *nowhere*. State where the cap is set (per run? per
   entity? token vs dollar?) in `operate/budget-and-cost` and `reference/configuration`.
   Currently I can configure thresholds I can't actually anchor.
2. **Testing: show how to run the tests.** `build/testing` describes *test packages*
   (`expected.yaml`) and *agent fixtures* but no command runs them, and `reference/cli` has
   no `swarm test`. Add the command(s), the fixture file format, and the directory
   convention — or mark these as not-yet-shipped like fork is.
3. **`swarm run` vs `swarm serve`: cross-reference at first contact.** The distinction is
   resolved well, but only in `operate/running-the-runtime` (~25 pages in). Add one line to
   quickstart/installation: "run = one-shot in-process; serve = long-running."
4. **Sequencing: root vs child flow.** The constraint drives rules in
   `concepts/agents-and-sessions` and `build/first-flow`, but is only defined in
   `build/composition` (much later). Add a one-paragraph primer (or a forward-link callout)
   the first time "root flow" / "child flow" appears.
5. **One end-to-end gate example.** `gate_state` is "Gate field definitions." with no shape;
   `sets_gate`/`clear_gates`/`entity.gates.x`/`flow_scope_key` are scattered. Add a single
   worked example: declare in `gate_state`, set it, guard on it, clear it.
6. **Reconcile `store_as` and `query` shapes.** `store_as: entity.composite` (accumulation)
   vs `store_as: composite_score` (patterns) — pick one or state both are valid. Same for
   `query:` as a map vs a list. These are copy-paste traps.
7. **OpenRPC vs OpenAPI naming.** Make the intro's "`openrpc.json` source of truth" match
   the shipped `openapi.json` (or vice-versa).
8. **`first-flow` trace shows `node/__runtime_replay_scope__`** where the prose says "the
   orchestrator." Re-capture with the real node id, or add a one-line note explaining the
   internal scope name. It's in the single most-read teaching trace on the site.
9. **Link `flow_scope_key` (and add a "Conversation" glossary entry).** Minor: connect the
   snake_case usages to the glossary's "Flow scope key", and add "Conversation" pointing to
   "Session".

### Nothing here is a structural problem
Every gap above is a fixable local issue (a missing command, an undefined value, a late
cross-reference), not a flaw in how the material is taught. The conceptual scaffolding is
sound and the teaching order is right. A motivated engineer can ship a real flow today; the
fixes above mostly remove avoidable friction and close two "documented but not runnable"
loops (budget cap, tests).
