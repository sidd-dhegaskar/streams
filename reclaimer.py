import time
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

STREAM = "jobs"
GROUP = "workers"
CONSUMER = "w1"          # the live consumer that takes over stuck jobs
MIN_IDLE_MS = 5000       # only claim entries idle for at least 5 seconds

# 1. list pending entries (the PEL) with their owner, idle time, delivery count
pending = r.xpending_range(STREAM, GROUP, min="-", max="+", count=10)

if not pending:
    print("nothing pending")
    raise SystemExit

for p in pending:
    print(f"pending {p['message_id']} owner={p['consumer']} "
          f"idle={p['time_since_delivered']}ms deliveries={p['times_delivered']}")

ids = [p["message_id"] for p in pending]

# 2. claim: move ownership to CONSUMER, but only entries idle >= MIN_IDLE_MS
claimed = r.xclaim(STREAM, GROUP, CONSUMER, min_idle_time=MIN_IDLE_MS, message_ids=ids)
print(f"claimed {len(claimed)} of {len(ids)} entries")

# 3. process each claimed job, then acknowledge it
for entry_id, fields in claimed:
    print(f"[{CONSUMER}] reprocessing {entry_id} {fields}")
    time.sleep(1)  # pretend to do work
    acked = r.xack(STREAM, GROUP, entry_id)
    print(f"[{CONSUMER}] acked {entry_id} (removed {acked} from PEL)")
