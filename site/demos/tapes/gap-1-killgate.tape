# Gap 1 — A bad prompt cannot ship just by passing eval.
# Shows: bene demo seeds a probe → experiments ls → the verdict is itself an engram

Output ../../assets/demos/gap-1-killgate.gif
Set Width 1100
Set Height 540
Set Theme "TokyoNight"
Set FontSize 16
Set FontFamily "JetBrains Mono"
Set TypingSpeed 30ms
Set PlaybackSpeed 1.3
Set Padding 20

Type "# Gap 1 — a bad prompt cannot ship just by passing eval."
Enter
Sleep 600ms

Type "uv run bene init"
Enter
Sleep 600ms

Type "DEMO_DB=$(uv run bene demo --no-ui 2>&1 | grep -oE '/tmp/bene-demo-[^ ]+/story.db' | head -1)"
Enter
Sleep 4500ms

Type "# every promote() must clear a sha256-locked probe"
Enter
Sleep 500ms

Type "uv run bene experiments ls --db $DEMO_DB | head -12"
Enter
Sleep 1800ms

Type "# verdict ACCEPT is itself an engram. Tamper the spec, the probe refuses."
Enter
Sleep 1200ms
