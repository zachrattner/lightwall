from datetime import datetime
import inspect

def now_ts():
    # ISO-like timestamp with milliseconds
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def info(msg):
    frame = inspect.stack()[1]
    filename = frame.filename
    lineno = f"{frame.lineno:06d}"
    level = "INFO  "
    print(f"[{now_ts()}] {filename}:{lineno} [{level}] {msg}")

def warning(msg):
    frame = inspect.stack()[1]
    filename = frame.filename
    lineno = f"{frame.lineno:06d}"
    level = "WARNING"
    print(f"[{now_ts()}] {filename}:{lineno} [{level}] {msg}")

def error(msg):
    frame = inspect.stack()[1]
    filename = frame.filename
    lineno = f"{frame.lineno:06d}"
    level = "ERROR  "
    print(f"[{now_ts()}] {filename}:{lineno} [{level}] {msg}")
