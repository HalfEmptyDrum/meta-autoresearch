# Optimizing the Optimizer of the Optimizer

A fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch) that adds cross-session memory.

## The problem

Autoresearch lets an AI agent run ~100 training experiments overnight, keeping improvements and discarding regressions. But the agent has no memory between sessions. Every session it re-discovers that batch size matters, wastes experiments on GELU again, re-learns that doubling width OOMs. The human reads `results.tsv` each morning and mentally tracks what worked — but that knowledge stays in their head.

## What this fork adds

Two scripts that build a persistent knowledge base across sessions:

- **`score_session.py`** — reads `results.tsv` and outputs structured session diagnostics (best bpb, keep rate, crash rate, longest plateau, improvement per experiment)
- **`update_discoveries.py`** — reads `results.tsv` and updates `discoveries.md`, a cross-session knowledge base of what worked, what failed, and what's worth exploring

After each session, run:

```bash
python score_session.py results.tsv
python update_discoveries.py results.tsv
```

The next session's agent reads `discoveries.md` at startup — skipping known dead ends, prioritizing proven winners, and picking up where the last session left off.

## Why this is meta-meta-programming

```
Layer 0:  THE MODEL        — weights being trained
Layer 1:  THE RESEARCHER   — AI agent modifying train.py based on val_bpb
Layer 2:  THE PROGRAMMER   — human writing program.md to guide the researcher
Layer 3:  THE SCRIPTS      — programs that update what the researcher knows
```

The agent at Layer 1 optimizes `train.py`. Our scripts optimize the agent's *knowledge* — what it tries, what it avoids, what it prioritizes. That's Layer 2 work done automatically. The human wrote `program.md` once; the scripts keep `discoveries.md` current.

See [META.md](META.md) for the full explanation.

## What `discoveries.md` looks like

After a few sessions, `discoveries.md` accumulates structured findings:

```markdown
## Kept Improvements
- increase LR to 0.04: +0.0047 bpb improvement [mar9]
- halve batch size: +0.0004 bpb improvement [mar9]

## Dead Ends
- switch to GeLU activation: -0.0118 bpb [mar9]

## Crashes
- double model width (OOM) [mar9]

## Promising But Unfinished
- RoPE base frequency 50000: missed by 0.0002 bpb [mar10]

## Session History
- **mar9**: 83 experiments, 15 kept, 6 crashed, best bpb=0.977123
- **mar10**: 91 experiments, 12 kept, 3 crashed, best bpb=0.974891
```

## Project structure

```
prepare.py              — data prep + runtime utilities (do not modify)
train.py                — model, optimizer, training loop (agent modifies this)
program.md              — agent instructions (reads discoveries.md at startup)
score_session.py        — session scoring
update_discoveries.py   — builds/updates discoveries.md from results
META.md                 — explains the meta-meta-programming layer
```

## License

MIT
