# Gap 3 — Computed trust, not a YAML knob.
# Helper: _show_trust.sh extracts the first agent + emits the trust JSON.

Output ../../assets/demos/gap-3-trust.gif
Set Width 1100
Set Height 600
Set Theme "TokyoNight"
Set FontSize 16
Set FontFamily "JetBrains Mono"
Set TypingSpeed 30ms
Set PlaybackSpeed 1.3
Set Padding 20

Type "# Gap 3 — L4 is the only level a human grants by name."
Enter
Sleep 600ms

Type "uv run bene init"
Enter
Sleep 600ms

Type "DEMO_DB=$(bash site/demos/tapes/_extract_demo_db.sh)"
Enter
Sleep 4500ms

Type "# 4 signals fold into a [0,1] composite — verification, audit, checkpoint, outcome"
Enter
Sleep 500ms

Type "bash site/demos/tapes/_show_trust.sh $DEMO_DB"
Enter
Sleep 2500ms

Type "# no YAML knob. L4 grant must declare granted_by='human:<name>' or the API raises."
Enter
Sleep 1200ms
