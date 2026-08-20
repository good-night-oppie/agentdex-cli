import subprocess

try:
    print(subprocess.check_output(["gh", "auth", "status"], stderr=subprocess.STDOUT).decode())
except Exception as e:
    print(e)
