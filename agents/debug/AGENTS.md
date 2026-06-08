# agents/debug — agentdex-cli

## Failure modes seen in the wild
- TODO: top 5 ways things break + their signatures

## Log locations
- TODO: where to tail when X breaks

## Sense tools
```bash
./tools/agent_senses/tail_logs.sh <area>
./tools/agent_senses/run_tests.sh
./tools/agent_senses/peek_metrics.sh
```

## Doom-loop guard (G4 LangChain ep4)
If you edit the same file > 5 times in one session AND tests still fail — STOP. Re-read `IDEAL_EXPERIENCE.md` + escalate.
