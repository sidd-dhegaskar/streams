import sys
import time
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

STREAM = "jobs"
GROUP = "workers"
consumer = sys.argv[1]  # e.g. python worker.py w1

print(f"[{consumer}] started, waiting for jobs...")

while True:
    # reply shape: [[stream_name, [(entry_id, {field: value}), ...]]]
    # or [] if block timed out with nothing new
    reply = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=1, block=2000)
    if not reply:
        continue

    for stream_name, entries in reply:
        for entry_id, fields in entries:
            print(f"[{consumer}] got {entry_id} {fields}")
            time.sleep(15)  # pretend to do work
            r.xack(STREAM, GROUP, entry_id)

