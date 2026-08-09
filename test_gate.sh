git diff --numstat HEAD~1 HEAD > /tmp/tiny-pr-numstat.txt
python3 scripts/tiny_pr_gate.py --body-file <(git log -1 --format=%B) --numstat-file /tmp/tiny-pr-numstat.txt
