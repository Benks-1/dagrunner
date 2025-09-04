import sys
from datetime import datetime

def say_hello():
    print(f"[mypkg.entry.say_hello] Hi from function at {datetime.now().isoformat(timespec='seconds')}")
    return {"status": "ok", "source": "say_hello"}

def add(a, b=0):
    total = a + b
    print(f"[mypkg.entry.add] a={a}, b={b}, total={total}")
    return total

def echo_args_kwargs(*args, **kwargs):
    print(f"[mypkg.entry.echo_args_kwargs] args={args} kwargs={kwargs}")
    # Return something JSON-serializable
    return {"args": list(args), "kwargs": kwargs}

def noisy():
    print("[mypkg.entry.noisy] normal print to STDOUT")
    print("[mypkg.entry.noisy] simulated warning on STDERR", file=sys.stderr)
    return "done"
