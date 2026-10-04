import time
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

STREAM = "jobs"
GROUP = "workers"
CONSUMER = "w1"
MIN_IDLE_MS = 5000

cursor = "0-0"       # where the scan starts; "0-0" = beginning of the PEL
total = 0

while True:
    result = r.xautoclaim(STREAM, GROUP, CONSUMER,
                          min_idle_time=MIN_IDLE_MS, start_id=cursor, count=10)
    # Redis 7 reply: [next_cursor, claimed_entries, deleted_ids]
    cursor, claimed = result[0], result[1]

    for entry_id, fields in claimed:
        print(f"[{CONSUMER}] reprocessing {entry_id} {fields}")
        time.sleep(1)  # pretend to do work
        acked = r.xack(STREAM, GROUP, entry_id)
        print(f"[{CONSUMER}] acked {entry_id} (removed {acked} from PEL)")
        total += 1

    if cursor == "0-0":   # Redis says the scan reached the end
        break

print(f"done, reclaimed {total} entries")
