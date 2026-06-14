# Gap 4 — Source of truth is a file on disk. cp, rsync, sqlite3 — every tool that speaks SQLite works.

Output ../../assets/demos/gap-4-sqlite.gif
Set Width 1100
Set Height 560
Set Theme "TokyoNight"
Set FontSize 16
Set FontFamily "JetBrains Mono"
Set TypingSpeed 30ms
Set PlaybackSpeed 1.3
Set Padding 20

Type "# Gap 4 — bene.db is plain SQLite on disk. no vendor portal between you and the truth."
Enter
Sleep 600ms

Type "uv run bene init"
Enter
Sleep 600ms

Type "DEMO_DB=$(bash site/demos/tapes/_extract_demo_db.sh)"
Enter
Sleep 4500ms

Type "# the file: real path, real size, openable by any tool"
Enter
Sleep 500ms

Type "bash site/demos/tapes/_show_sqlite.sh $DEMO_DB"
Enter
Sleep 2500ms

Type "# at 03:00 you reach for this file. not a dashboard you're waiting on."
Enter
Sleep 1200ms
