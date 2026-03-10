# Optimizing the Optimizer of the Optimizer

## The Three Layers Today

```
Layer 0:  THE MODEL        — weights being trained
Layer 1:  THE RESEARCHER   — AI agent modifying train.py based on val_bpb
Layer 2:  THE PROGRAMMER   — human writing program.md to guide the researcher
```

The agent at Layer 1 has no memory. Every session starts from scratch — it re-discovers that batch size matters, wastes experiments on GELU again, re-learns that doubling width OOMs. The human at Layer 2 knows all of this from reading past results, but has no mechanism to pass that knowledge down except rewriting program.md by hand.

## What We're Building

Two scripts that close this gap:

**`score_session.py`** reads `results.tsv` and computes structured diagnostics: best bpb achieved, keep rate, crash rate, longest plateau, improvement per experiment. This is the **loss function for Layer 2** — it turns a raw experiment log into a signal about how well the *strategy* worked, not just how well the *model* trained.

**`update_discoveries.py`** reads `results.tsv` (and optionally the existing `discoveries.md`) and produces an updated `discoveries.md` — a persistent knowledge base of what worked, what failed, and what's worth exploring further. The agent reads this file at the start of every session.

Together they form a feedback loop:

```
Session N runs  ──>  results.tsv
                         │
              score_session.py analyzes it
                         │
              update_discoveries.py distills findings
                         │
                         v
                   discoveries.md  (persistent cross-session memory)
                         │
                         v
              Session N+1 reads it at startup
              ──>  skips known dead ends
              ──>  prioritizes known winners
              ──>  picks up where N left off
```

## Why This Is Layer 3, Not Layer 1

The agent at Layer 1 optimizes `train.py` using `val_bpb` as its signal. It does not modify its own instructions. It does not change how it searches.

`update_discoveries.py` modifies what the agent *knows before it starts* — which changes what it tries, in what order, and what it avoids. It's optimizing the **research strategy**, not the training code. That's Layer 2 work (modifying the agent's effective instructions), done automatically instead of by a human.

The key distinction:

| | What it modifies | Signal it uses | Who runs it |
|---|---|---|---|
| Layer 1 (agent) | `train.py` | `val_bpb` | AI agent, every 5 min |
| Layer 2 (human) | `program.md` | reading results.tsv + intuition | Human, once per day |
| **Our scripts** | `discoveries.md` (read by agent) | `results.tsv` via `score_session.py` | Automated, after each session |

Our scripts do what the human at Layer 2 does — read results, identify patterns, update the agent's knowledge — but automatically and systematically. The human wrote `program.md` once; the scripts keep `discoveries.md` current. This is meta-programming: a program that improves the programmer.

## Why Not a Full Outer Loop?

The full version would be a `metarun.py` orchestrator that spawns sessions, scores them, feeds results to a meta-agent, modifies `program.md`, and runs the next session in a keep/discard loop.

That requires solving agent orchestration — programmatically spawning and managing multi-hour AI agent sessions. That's framework-specific, complex, and the tooling doesn't reliably exist yet.

`score_session.py` + `update_discoveries.py` deliver most of the value without any of that complexity:

- **No agent orchestration needed.** The human still starts each session manually (or via cron). The scripts run between sessions.
- **No statistical significance problem.** We're not comparing program.md variants — we're accumulating knowledge. Every session makes discoveries.md better, regardless of variance.
- **No cost multiplication.** No need for 2-3 runs per variant. One session, one update, one improvement.
- **Immediately useful.** Works with the existing autoresearch setup. No new infrastructure. Just run `python update_discoveries.py results.tsv` after a session and start the next one.

The full outer loop is the ceiling. This is the floor that's already worth standing on.

## What It Looks Like In Practice

After your first session:
```
$ python score_session.py results.tsv
{
  "final_best_bpb": 0.9812,
  "keep_rate": 0.23,
  "crash_rate": 0.08,
  "max_plateau": 14,
  ...
}

$ python update_discoveries.py results.tsv
Updated discoveries.md: 8 high-value findings, 5 dead ends, 3 promising leads.
```

Before your second session, the agent reads `discoveries.md` and starts from knowledge, not ignorance. By session 5, the agent has a substantial knowledge base and wastes almost no experiments on things that have already been tried.

The human's role shifts from "read 100 experiment rows and figure out patterns" to "glance at discoveries.md and make sure it looks sane." That's the meta-meta-programming payoff — and it doesn't require a single line of agent orchestration code.
