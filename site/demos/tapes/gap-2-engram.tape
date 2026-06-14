# Gap 2 — Cross-agent memory with provenance, on a typed ladder.
# Helper: _show_engrams.sh runs the bene query so the tape stays quote-free.

Output ../../assets/demos/gap-2-engram.gif
Set Width 1100
Set Height 600
Set Theme "TokyoNight"
Set FontSize 16
Set FontFamily "JetBrains Mono"
Set TypingSpeed 30ms
Set PlaybackSpeed 1.3
Set Padding 20

Type "# Gap 2 — the next agent walks in and greps what the last one learned."
Enter
Sleep 600ms

Type "uv run bene init"
Enter
Sleep 600ms

Type "DEMO_DB=$(bash site/demos/tapes/_extract_demo_db.sh)"
Enter
Sleep 4500ms

Type "# typed engrams across tiers — trace, episodic, semantic, procedural, strategic"
Enter
Sleep 500ms

Type "bash site/demos/tapes/_show_engrams.sh $DEMO_DB | head -22"
Enter
Sleep 2200ms

Type "# provenance is mandatory. promotion never mutates sources."
Enter
Sleep 1200ms
