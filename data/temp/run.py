import subprocess, sys, io, re, os
args = sys.argv[1:]
out_path = os.environ.get("TB_OUT", "data/temp/tb_out.txt")
r = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "--no-header", "--tb=short", "-p", "no:logging", "--show-capture=no"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
lines = [l for l in r.stdout.splitlines() if not l.strip().startswith('{"timestamp"')]
io.open(out_path, "w", encoding="utf-8").write("\n".join(lines))
print("exit", r.returncode, "->", out_path)
