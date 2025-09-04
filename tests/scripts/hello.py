from datetime import datetime
import sys

print(f"[scripts.hello] Hello from script at {datetime.now().isoformat(timespec='seconds')}")
print("[scripts.hello] This is STDOUT.")
print("[scripts.hello] Writing something to STDERR...", file=sys.stderr)
