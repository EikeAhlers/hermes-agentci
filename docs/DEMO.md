# 90-second demo — shot list

One take, terminal only, no cuts inside the proof.

## Before recording

```bash
cd ~/projects/hermes-agentci && python -m agentci init /tmp/demo/agentci.toml
python -m agentci run /tmp/demo/agentci.toml --parallel 2      # warm-up, produces a baseline
```

## Shot list (85 s)

| Time | On screen | Say |
|---|---|---|
| 0–10 s | `git diff` of a prompt file + `python -m pytest` green | "My code is tested. My agent is not. I change one sentence in a prompt and hope." |
| 10–25 s | `cat agentci.toml` — two cases, assertions visible | "So I write tests for the agent: a prompt, a fixture, and the evidence that proves it worked — files on disk, tools used, tokens burned." |
| 25–42 s | `python -m agentci run agentci.toml --parallel 2` → 2/2 pass, tokens, time | "Two real Hermes runs in throwaway workspaces. Both green: 8.022 tokens, 25 seconds. Report is HTML, result is JSON." |
| 42–55 s | change one expected word, re-run → FAIL + `echo $?` = 1 | "One word in the assertion — and the build goes red. Exit code 1, so this gates a PR like any other test." |
| 55–70 s | `agentci matrix … --models a,b` | "And the same suite across models: same result, but the fast model needs 40% fewer tokens. That's a decision I can measure now." |
| 70–85 s | `report.html` in browser, baseline diff line | "Regressions, fixes and token deltas against the previous run — no vibes, just evidence." |

## Voice-over (short)

> "agentci is CI for your agent: prompt cases in isolated workspaces, judged on the session record
> and the files on disk. Exit code 1 when behaviour regresses, and a matrix that shows which model
> passes cheapest. Tests for agents — evidence, not vibes."

## Caption

> agentci for @NousResearch Hermes: write tests for your agent, not just your code. Isolated runs,
> assertions on real evidence (tokens, tools, file hashes), CI exit codes, model matrix.
> https://github.com/EikeAhlers/hermes-agentci
