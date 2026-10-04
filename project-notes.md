# Redis Streams Job Queue: Project Notes

Covers Steps 1 to 3 (stream, producer, consumer group). Later steps (ACK, PEL, claim, at-least-once) are not covered yet.

---

## 1. The problem this solves

A **job queue** lets one part of a system (the *producer*) hand work to another part (the *worker*) without waiting for it. The work runs later, possibly on a different machine.

Requirements for a useful queue:
1. Jobs are stored durably and in order.
2. Many workers can share the work, and each job goes to only one worker.
3. If a worker crashes mid-job, the job is not lost (Steps 4 to 6, still to come).

Redis Streams meet all three. A Redis list would not meet 3: `LPOP` removes the job, so a worker that crashes after popping takes the only copy with it.

---

## 2. System design (so far)

```
                         Redis (redis:7-alpine, port 6379)
                    +-----------------------------------------+
                    |  Stream "jobs"                          |
 producer.py  --->  |  [id1][id2][id3][id4] ... append-only   |
   XADD             |                ^                        |
                    |   group "workers"                       |
                    |   last-delivered ID (shared bookmark)   |
                    +----------+----------------+-------------+
                               | XREADGROUP     | XREADGROUP
                               v                v
                          worker.py w1     worker.py w2
```

Components and why each exists:

| Component | Why it exists |
|---|---|
| **Stream `jobs`** | Durable, ordered, append-only storage for jobs. Reading never removes entries, so a job still exists if a worker dies. |
| **Entry ID** (`<ms-timestamp>-<seq>`) | Unique, ever-increasing stamp that fixes the order and identifies one job. |
| **Producer** | Only appends jobs. It knows nothing about workers or groups, so the two sides are decoupled. |
| **Consumer group `workers`** | A named team sharing the stream, so each job goes to exactly one member. |
| **Last-delivered ID** | The group's shared bookmark: "the next never-delivered entry". Stored per group, not per worker. |
| **Consumer (worker)** | Pulls jobs for the group by name. Redis creates the consumer the first time the name is used. |

Key design properties:
- **Pull model.** Workers ask for a job when they are free, and Redis gives the next unclaimed entry to whoever asks first. A fast worker gets more jobs than a slow one (a 1s worker beats a 3s worker roughly 3 to 1). This is load balancing for free. A 5/5 split is typical but not guaranteed. The guarantee is only that each job goes to exactly one worker.
- **Delivery is not completion.** In Step 3 the workers never confirmed completion. Redis recorded the deliveries anyway. That record is the Pending Entries List, the subject of Step 4.
- **Comparison with Kafka (which you know).** A consumer group with a shared position is similar. The difference is that Kafka tracks one offset per partition, while Redis will track each individual unconfirmed entry (coming in Step 4).

---

## 3. Commands used and why

### Docker

```
docker run -d --name redis-streams -p 6379:6379 redis:7-alpine
```
- `-d` runs it in the background. `--name` gives the container a name we can refer to later.
- `-p 6379:6379` maps the container's Redis port to your machine, so Python on Windows can connect to `localhost:6379`.
- `redis:7-alpine` is the small image the README specifies.

```
docker exec -it redis-streams redis-cli
```
- Runs `redis-cli` (Redis's command-line client) inside the running container. `-it` makes it interactive. We use it to inspect the stream by hand.

### Redis commands

| Command | What it does | Why we used it |
|---|---|---|
| `XADD jobs * task resize file a.png` | Appends an entry to stream `jobs`. `*` means "Redis, generate the ID". Returns the new ID. | This is how a job is enqueued. |
| `XRANGE jobs - +` | Returns entries between two IDs. `-` is the smallest possible ID and `+` the largest, so this returns everything. | To see that reads don't remove entries, and to inspect jobs. |
| `XLEN jobs` | Number of entries in the stream. | To confirm the producer's jobs arrived. |
| `DEL jobs` | Deletes the whole key, including its groups. | To reset to a clean state between experiments. |
| `XGROUP CREATE jobs workers 0` | Creates group `workers` on stream `jobs`, with the bookmark at `0`. | So workers can share jobs. `0` means "start from the beginning, existing entries count as new". |
| `XGROUP CREATE jobs workers $` | Same, but `$` places the bookmark at the current end of the stream. | Break-it experiment: only entries added after creation are delivered. |
| `XGROUP DESTROY jobs workers` | Deletes the group and its bookmark, but not the stream's entries. | To recreate the group with a different starting point. |
| `XREADGROUP GROUP workers w1 COUNT 2 STREAMS jobs >` | Asks for new entries on behalf of consumer `w1` in group `workers`. | To see the reply shape by hand. Running it twice returns different entries because the bookmark moved. |
| `XPENDING jobs workers` | Shows delivered-but-unconfirmed entries (introduced as a teaser; covered in Step 4). | Preview of the PEL. |

### Python (redis-py)

```python
r = redis.Redis(host="localhost", port=6379, decode_responses=True)
```
- `decode_responses=True` makes Redis replies come back as normal strings instead of bytes.

```python
entry_id = r.xadd("jobs", {"task": "resize", "file": "a.txt", "job_number": i})
```
- Same as `XADD jobs *`. Takes the stream name and a dict of fields. Returns the entry ID. Values are stored as strings, so `i = 3` comes back as `"3"`.

```python
reply = r.xreadgroup("workers", consumer, {"jobs": ">"}, count=1, block=2000)
```
| Argument | Meaning |
|---|---|
| `"workers"` | Group name. Must match `XGROUP CREATE`, or Redis returns `NOGROUP`. |
| `consumer` | This worker's name (from `sys.argv[1]`, e.g. `w1`). |
| `{"jobs": ">"}` | Stream name to starting ID. `>` means "only entries never delivered to anyone in this group". Using a real ID such as `0` instead returns this consumer's own pending entries (needed in Step 5). |
| `count=1` | Max entries per call. One at a time makes the split between workers easy to see. |
| `block=2000` | Wait up to 2000 ms when nothing is new, instead of returning immediately. Avoids busy-polling (a loop spinning at full CPU). `block=0` means wait forever. If it times out, the reply is `[]`. |

Reply shape:
```
[ ["jobs", [ ("1700000000000-0", {"task": "resize", "file": "a.txt"}) ]] ]
```
List of streams, each a pair of stream name and a list of entries. Each entry is a pair of entry ID and a dict of fields. That's why the worker uses two nested `for` loops.

---

## 4. The code

- `producer.py`: loops 10 times, calling `xadd` for each job and printing the returned ID.
- `worker.py <name>`: loops forever on `xreadgroup`. On an empty reply it goes round again. For each entry it prints it, then sleeps 1 second to simulate work. It deliberately does not `XACK` yet.

---

## 5. Concepts learned

1. **Stream:** append-only list of entries. Reads don't remove anything.
2. **Entry ID:** `<ms-timestamp>-<sequence>`, increasing, fixes order.
3. **XADD:** appends an entry and returns its ID. The returned ID is the producer's receipt (for logging, tracing, `XRANGE` lookups). Consumers don't need it from the producer, because each entry arrives with its ID when read.
4. **Consumer group:** a named team sharing a stream. Each entry goes to exactly one member.
5. **Last-delivered ID:** the group's shared bookmark. Only entries after it are handed out with `>`.
6. **XREADGROUP:** pulls new entries for a named consumer and moves the bookmark.

### Things I got wrong or refined along the way
- Reading never removes entries, but entries can still be removed deliberately (`XDEL`, `XTRIM`). Removal is a separate action.
- With `$`, old jobs were skipped because they sat *before* the bookmark, not because they were "already assigned".
- "Exactly 5 each" is not guaranteed. The split depends on who asks first (pull model).

---

## 6. Step 4: Acknowledgement and the PEL

### 6.1 The key idea: Redis keeps TWO separate things

**Thing 1: the stream `jobs`** is the ledger of all jobs ever added.
- `XADD` adds to it, `XLEN jobs` counts it, `XRANGE jobs - +` reads it.

**Thing 2: the PEL (Pending Entries List)** belongs to a *group*. It is a to-do list: "these jobs were handed out and not confirmed yet". It stores IDs, owners, idle times and delivery counts, not the jobs themselves.
- `XREADGROUP ... >` **adds** an entry to it.
- `XACK` **removes** an entry from it.
- `XPENDING jobs workers` reads it.

```
XADD             -> entry in STREAM
XREADGROUP >     -> entry ALSO in PEL (owner = the consumer that got it)
worker finishes
XACK             -> entry leaves PEL   (still in STREAM!)
```

| Command | Changes the stream? | Changes the PEL? |
|---|---|---|
| `XADD` | Yes, adds | No |
| `XREADGROUP >` | No | Yes, adds |
| `XACK` | **No** | Yes, removes |
| `XTRIM` / `XDEL` | Yes, removes | No |

**Delivery is not completion.** `XREADGROUP` returning a job does not mean it is done. It stays in the PEL until `XACK`. This is the misconception most beginners have.

**Can things be removed from the PEL?** Yes. `XACK` is the normal way. A stuck entry can still be ACKed later, or (Step 5) claimed by another consumer, finished, and ACKed. `XGROUP DESTROY` also deletes the whole PEL along with the group.

**Why Redis is designed this way:** nothing is deleted on read or confirm, so a crashed worker's job still exists and another worker can take over. Several groups can also read the same stream independently, each with its own bookmark and PEL (a new group created with `0` would receive all the old jobs again).

**The cost:** the stream grows forever unless you trim it. A stream that is "not shrinking" is **normal**, not a bug.

### 6.2 The updated worker

```python
r.xack(STREAM, GROUP, entry_id)   # after the work is done
```
- Arguments: stream name, group name, the entry ID to confirm (from the reply).
- Returns the number of entries removed from the PEL. It returns `0` if the ID was not pending, or if you passed the **wrong stream or group name**. Redis does not raise an error in that case, so a typo fails silently.
- ACK only after the work succeeded. If the worker crashes before the ACK, the entry stays pending and can be recovered.

### 6.3 Commands used in Step 4

| Command | What it does | Where to use it |
|---|---|---|
| `XPENDING jobs workers` | Summary: total pending, smallest ID, largest ID, count per consumer. | First check: is the PEL growing? |
| `XPENDING jobs workers - + 10` | Detail: up to 10 rows of `[id, owner, idle ms, delivery count]`. | Find which entries are stuck and who owns them. |
| `XACK jobs workers <id>` | Removes one entry from the PEL. Returns `1` or `0`. | After finishing a job. Also useful by hand to clear a stuck entry. |
| `XINFO CONSUMERS jobs workers` | Lists each consumer with `pending` (unconfirmed jobs it holds) and `idle` (ms since that *consumer* last talked to Redis). | Judge whether a worker is alive or silent. |
| `XTRIM jobs MAXLEN 1000` | Cuts the stream down to about the newest 1000 entries. | Cap memory in production. |
| `XADD jobs MAXLEN ~ 1000 * k v` | Adds a job and trims at the same time. `~` means "approximately", so Redis can trim in cheap chunks. | Same, without a separate command. |
| `XGROUP CREATE jobs workers 0 MKSTREAM` | Creates the group, and creates an empty stream if none exists. | Set up a group before any jobs exist. |

Reading the detail row, for example:
```
1) "1791115061107-0"   <- entry ID
2) "w2"                <- owner (consumer it was delivered to)
3) (integer) 784456    <- idle time in ms (~13 min since last delivery)
4) (integer) 1         <- delivery count (times Redis has handed it out)
```
- **Idle time** grows every second nothing touches the entry, and resets to near zero when the entry is delivered again (e.g. claimed in Step 5).
- **Delivery count** goes up by 1 on each redelivery. Later it tells you whether a job keeps failing.

Warning: trimming can delete entries that are still pending, so the PEL then points to jobs that no longer exist. Trim only after acknowledgement.

### 6.4 Idle time and its limit

Idle time measures only "time since last delivery". It cannot say why.

| Situation | What `XPENDING` shows |
|---|---|
| Worker **crashed** after taking the job | Large, growing idle time |
| Worker **alive but running a very slow job** | Large, growing idle time |

They look identical, so idle time is a clue, not proof. More evidence: `XINFO CONSUMERS` (a consumer whose own idle keeps climbing while others stay small has probably stopped, though a busy worker also isn't calling Redis). This uncertainty is why Step 5 uses an idle *threshold*: too low and you steal jobs from healthy workers.

### 6.5 Experiment results from my runs
- With ACK in both workers, jobs split and the PEL ended up empty.
- With one no-ack worker (`w2`), the jobs split 3 (ACKing) / 7 (no-ack) and `XPENDING` showed `w2` with 7 pending.
- After waiting, Redis **did not** reassign those 7 jobs to the idle healthy worker. Redis never redelivers on its own. Recovery is code we must write (Step 5).

### 6.6 Errors I hit
- **`NOGROUP No such key 'jobs' or consumer group 'workers'`**: the stream or group did not exist. `DEL jobs` deletes the stream and every group inside it. Fix: run the producer (creates the stream), then `XGROUP CREATE jobs workers 0`, then start the workers. Or use `MKSTREAM`.

### 6.7 Things I got wrong in Step 4
- Thought `XACK` shrinks the stream. It does not. It only removes the entry from the PEL.
- Thought idle time alone separates crashed from slow workers. It does not.
- Thought entries cannot be removed from the PEL. They can (`XACK`).
- Listed "ACKs not enabled" and "ACK sent to the wrong stream" as two causes, but they are the same family. Other causes: a crashed consumer, a stuck or slow job.

---

## 7. Step 4 check questions (answer in my own words)

1. **Idle time:** two workers each hold a pending entry idle for 10 minutes: one crashed, one alive but slow. Can the idle column tell which is which? Name one command that gives more evidence and what it shows.
2. **Stream vs PEL:** after all 10 jobs are acknowledged, what do `XLEN jobs` and `XPENDING jobs workers` output, and why do they differ? If I run `XGROUP CREATE jobs newgroup 0` and start a worker in `newgroup`, does it receive the 10 old jobs? Why?
3. **Debugging:** "The PEL keeps growing and the stream isn't shrinking." Give at least two causes for the PEL growing, the command to tell them apart, and say whether the stream not shrinking is a bug.

---

## 8. Step 5: Crash and reclaim

### 8.1 The problem
A worker takes a job (it enters the PEL, owner = that worker) and then **crashes** before `XACK`. The entry stays in the PEL owned by a dead consumer. From Step 4 we know **Redis never redelivers on its own**, so without extra code the job is stuck forever. Recovery is code we write: some live process must notice the stuck entry and take it over.

### 8.2 Key concepts

**Claiming** = moving ownership of a pending entry from one consumer to another. After a claim, the entry is in the PEL under the new owner, and the new owner is expected to finish it and `XACK`.

**Min-idle-time (the timeout).** A claim command takes a threshold in milliseconds. Redis only claims an entry if its idle time is **at least** that threshold. This is the "idle timeout" from the README. It is the safety check against stealing jobs from workers that are merely slow.

**What a successful claim changes** (this matters):
1. The owner becomes the claimer.
2. The **idle time resets to ~0**.
3. The **delivery count goes up by 1** (the entry has now been handed out once more).

Because the idle time resets, an entry that was just claimed no longer passes the min-idle check for anyone else. That is the built-in guard against two claimers taking the same entry.

### 8.3 The commands

**`XCLAIM <stream> <group> <new-consumer> <min-idle-ms> <id> [<id> ...]`**
- You must already know the entry IDs (find them with `XPENDING jobs workers - + 10`).
- For each ID: if the entry is pending and its idle time >= `min-idle-ms`, ownership moves to `<new-consumer>`. IDs that fail the check are skipped.
- Returns the claimed entries (ID and fields), so the claimer has the job data right away. Add `JUSTID` to get only IDs (and then the delivery count is NOT incremented).
- Example: `XCLAIM jobs workers w1 5000 1791115061107-0`

**`XAUTOCLAIM <stream> <group> <new-consumer> <min-idle-ms> <start-id> [COUNT n]`** (Redis 6.2+; the 7-alpine image has it)
- Does the "find idle entries + claim them" job in one call, so you don't need `XPENDING` first.
- `<start-id>` is a cursor. Start with `0-0`. The reply includes a **next cursor** to pass as `<start-id>` on the next call (it is `0-0` when the scan is finished).
- Reply (Redis 7): `[next-cursor, [claimed entries], [IDs that were pending but deleted from the stream]]`.
- Example: `XAUTOCLAIM jobs workers w1 5000 0-0 COUNT 10`

Which one to use: `XCLAIM` makes each step visible (good for learning, the README asks for it). `XAUTOCLAIM` is what you would use in a real reclaim loop.

### 8.4 redis-py versions

```python
# list pending entries as dicts
r.xpending_range("jobs", "workers", min="-", max="+", count=10)
# -> [{"message_id", "consumer", "time_since_delivered", "times_delivered"}, ...]

# claim specific entries
claimed = r.xclaim("jobs", "workers", "w1", min_idle_time=5000, message_ids=[some_id])
# -> [(entry_id, {fields}), ...]   (empty list if the idle check failed)

# claim automatically
next_id, entries, deleted = r.xautoclaim("jobs", "workers", "w1",
                                          min_idle_time=5000, start_id="0-0", count=10)
```
`min_idle_time` and `message_ids` argument names are the redis-py ones. Check the return shapes by printing them once, the shape can differ between redis-py versions.

### 8.5 Simulating a crash
- A normal `Ctrl+C` in the worker raises `KeyboardInterrupt` while it is inside `time.sleep(...)`, before the `xack` line. So the entry stays pending: a crash "mid-processing".
- To get a clear window, make the job slow (e.g. sleep 10 s) so you can kill the worker during it.
- A real crash (power loss, `kill -9`) behaves the same from Redis's point of view: the connection disappears, nothing is ACKed, nothing is cleaned up. Redis does not notice or react.

### 8.6 The recovery flow
```
w2 takes job X  (PEL: X owned by w2, delivery count 1)
w2 crashes      (nothing changes in Redis; X's idle time keeps growing)
...idle time passes the threshold...
reclaimer: XCLAIM / XAUTOCLAIM as w1   (X owned by w1, idle reset, delivery count 2)
w1 processes X, then XACK              (X leaves the PEL)
```

### 8.7 Picking the threshold
- Too **low** (below a job's normal run time): a healthy worker's job looks stuck, gets claimed, and now **two workers run the same job**.
- Too **high**: a real crash takes a long time to recover from.
- Rule of thumb: comfortably above the longest normal run time of a job.
- Idle time cannot distinguish crashed from slow (Section 6.4), so this threshold is always a guess. That is a fundamental property, not a bug. It leads straight into at-least-once delivery (Step 6).

### 8.8 How this differs from Kafka (which I know)
In Kafka, when a consumer dies, the group rebalances and the partition's committed offset tells the new consumer where to restart. In Redis there is no rebalance. Each in-flight entry has an explicit owner, so recovery means explicitly taking over those individual entries.

### 8.9 Step 5 check questions
1. What would happen if two reclaimers try to `XCLAIM` the same entry at the same moment? (Use 8.2: what does a successful claim do to idle time and the min-idle check?)
2. You set the min-idle-time lower than a job's normal run time. What happens to a slow-but-healthy worker's job, and what is the consequence?

### 8.10 Delivery count (the number in the 4th column of `XPENDING ... - + 10`)
- Stored per pending entry. It counts how many times Redis has handed that entry out.
- `XREADGROUP >` first delivery: 1. Every successful `XCLAIM` / `XAUTOCLAIM`: +1. `XACK` removes the entry and the counter with it.
- A count of 2 after one crash is normal. A count that keeps climbing (4, 5, 6...) suggests the **job itself** is the problem (a "poison message": it crashes every worker that takes it), or the threshold is too low and healthy workers keep losing their jobs.
- Use it in a reclaimer: "if count > N, don't retry forever, move it to a dead-letter stream". This is the final variation task.

### 8.11 Observations from my Step 5 runs
- Reclaimer with a low threshold (500 ms) claimed a job from a healthy 10 s worker. The job ran twice. When the original worker finally ran `XACK`, it returned `0` with no error, so nothing told it the job had been done already.
- Two claimers racing: the first successful claim resets idle time to ~0, so the second fails the min-idle check and gets nothing (the check and claim are one atomic operation in Redis).
- `XAUTOCLAIM` replaces "list the PEL, then `XCLAIM` the IDs" with one call and a cursor (`0-0` = start and finished).

---

## 9. Reference: how to read every output (the "schema")

### 9.0 Reading `redis-cli` output
`redis-cli` prints lists with numbered labels: `1)`, `2)`, ... The label is just the **position** in the list. The **value** is what follows it. Nested lists are indented and restart numbering. Example: in `4) (integer) 1` the `4)` is a label and the delivery count is the value `1`.

### 9.1 What is stored where

```
Redis key "jobs" (type: stream)
|
|-- entries (the ledger)                          <- XADD adds, XTRIM/XDEL removes
|     "1791124701949-0" -> {task: resize, file: a.txt, job_number: 0}
|     "1791124701949-1" -> {task: resize, file: a.txt, job_number: 1}
|     ...
|
|-- group "workers"
      |-- last-delivered-id  (bookmark for ">" reads)
      |-- consumers: w1, w2, ...      (created on first use)
      |-- PEL (to-do list of unconfirmed deliveries)
            entry-id -> { owner, last-delivery-time (-> idle), delivery-count }
```
Entry data lives in the stream only. The PEL stores bookkeeping about entries, not the jobs themselves.

### 9.2 Entry ID
`1791124701949-1` = `<milliseconds since 1970>-<sequence>`. The sequence separates entries created in the same millisecond. IDs only increase. Special IDs: `*` (on XADD: generate one), `-` / `+` (smallest / largest, in range commands), `0` (before everything), `$` (current end of stream, when creating a group), `>` (in XREADGROUP: never-delivered entries only), `0-0` (start/finished cursor in XAUTOCLAIM).

### 9.3 `XRANGE jobs - +` (read the ledger)
```
1) 1) "1791124701949-0"          <- entry ID
   2) 1) "task"                  <- field/value pairs, flattened
      2) "resize"
      3) "file"
      4) "a.txt"
```
List of entries; each entry is `[id, [field, value, field, value, ...]]`.

### 9.4 `XREADGROUP` reply
redis-cli: nested lists. redis-py (decode_responses=True):
```
[ [ "jobs", [ ("1791124701949-0", {"task": "resize", "file": "a.txt"}), ... ] ] ]
   ^stream   ^entries: (entry_id, fields_dict)
```
`[]` / nil means the `block` timeout passed with nothing new.

### 9.5 `XPENDING jobs workers` (summary)
```
1) (integer) 40            <- total pending entries in the group's PEL
2) "1791104330632-0"       <- smallest pending ID
3) "1791104813890-0"       <- largest pending ID
4) 1) 1) "w1"              <- per consumer:
      2) "40"              <-   [name, count of pending]  (count is a string)
```

### 9.6 `XPENDING jobs workers - + 10` (detail, one row per entry)
| Position | Meaning | Example |
|---|---|---|
| 1 | entry ID | `"1791124701949-1"` |
| 2 | owner (consumer holding it) | `"w2"` |
| 3 | idle time in ms (since last delivery) | `4656` |
| 4 | delivery count | `1` |

redis-py `xpending_range` gives the same as dicts: `message_id`, `consumer`, `time_since_delivered`, `times_delivered`.

### 9.7 `XINFO CONSUMERS jobs workers`
Per consumer (printed as name/value pairs):
- `name`: consumer name
- `pending`: how many unconfirmed entries it holds
- `idle`: ms since this consumer last interacted with Redis (not the same as an entry's idle time)
- (Redis 7.2+ also shows `inactive`: ms since it last successfully read or claimed. May not exist on older 7.x images, check the actual output.)

### 9.8 `XINFO GROUPS jobs` (Redis 7+; field list may vary a bit by version)
`name`, `consumers` (how many), `pending` (PEL size), `last-delivered-id` (the bookmark), and in newer versions `entries-read` and `lag` (entries in the stream the group has not yet been given).

### 9.9 `XCLAIM` / `XAUTOCLAIM` replies
- `XCLAIM`: the claimed entries, same shape as XRANGE: `[(id, fields), ...]`. With `JUSTID`, only the IDs. Empty if the min-idle check failed.
- `XAUTOCLAIM` (Redis 7): `[next_cursor, [claimed entries], [deleted IDs]]`.
  - `next_cursor`: pass as the next `start`. `0-0` means the scan is finished.
  - `claimed entries`: `[(id, fields), ...]`
  - `deleted IDs`: entries that were still in the PEL but had been removed from the stream (e.g. by `XTRIM`).

### 9.10 Return values to remember
| Call | Returns |
|---|---|
| `XADD` | the new entry ID |
| `XACK` | number of entries removed from the PEL (`0` = was not pending, or wrong stream/group, silently) |
| `XLEN` | number of entries in the stream (unchanged by XACK) |
| `XGROUP CREATE` | `OK` (error `BUSYGROUP` if it already exists, `NOGROUP`/key error if the stream is missing and no `MKSTREAM`) |
| `XGROUP DESTROY` | `1` if a group was deleted, `0` if not |

### 9.11 Common errors
- `NOGROUP No such key 'jobs' or consumer group 'workers'`: stream or group missing (often after `DEL jobs`).
- `BUSYGROUP Consumer Group name already exists`: you ran `XGROUP CREATE` twice. Destroy it first or skip.
- `IndexError` in `worker.py`: you forgot the consumer-name argument (`python worker.py w1`).

---

## 10. Poison messages

### 10.1 What it is
A **poison message** is a job whose own data or content makes processing fail every time (bad input, a bug it always triggers). Every worker that picks it up crashes or errors, no matter which worker it is.

Analogy: a parcel with a broken label. Whoever gets it can't deliver it, so it keeps coming back and going to the next courier, forever.

### 10.2 What it looks like in Redis
```
worker A takes entry X          -> delivery count 1, A crashes
reclaimer claims X for worker B -> count 2, B crashes
reclaimer claims X for worker C -> count 3, C crashes
...                             -> count keeps climbing, X never leaves the PEL
```
- The entry is never ACKed, so it stays in the PEL.
- Each claim adds 1 to the **delivery count** (the 4th field in `XPENDING ... - + 10`).
- Redis does nothing about it. It does not stop retrying. Without extra code, the job is retried forever and keeps killing workers.

### 10.3 Why it matters
- It wastes work and can crash worker after worker.
- It can hide healthy jobs behind it if workers keep failing on it.
- It is the reason delivery count exists as a number you can act on.

### 10.4 High delivery count: two causes, same symptom
| Cause | Job at fault? | What you'd see |
|---|---|---|
| **Poison message**: the job crashes every worker | Yes | Workers actually crash or error on this entry each time |
| **Threshold too low**: min-idle-time is shorter than the job's normal run time, so a healthy slow worker keeps getting its job stolen (Section 8.7) | No | Workers are alive and finish the job, but the entry keeps being claimed from them |

The count alone cannot tell these apart (both can show 4). Check the evidence: worker logs, `XINFO CONSUMERS` (are consumers going silent or still active?), and how long the job normally takes versus the threshold. This is the same "evidence, not proof" point as idle time (6.4).

### 10.5 How to handle it (idea for the final variation task)
Do not retry forever. Set a max attempts limit, for example 3:
1. In the reclaimer, read the delivery count of each pending entry (`times_delivered` in `xpending_range`, or the 4th field in `XPENDING`).
2. If the count is **above the limit**, do not process it again. Instead:
   - copy the entry's fields to a **dead-letter stream** (e.g. `jobs:dead`) with `XADD`, so a human can inspect it,
   - then `XACK` it in the main group so it leaves the PEL.
3. If the count is within the limit, claim and retry as normal.

Points to think about when I build it:
- **Order of operations:** if the reclaimer crashes between copying to the dead-letter stream and the `XACK`, the entry could be dead-lettered twice or retried again. Which order is safer, and what does that choice give up? (Ties into at-least-once delivery, Step 6.)
- The limit should be set above the number of retries you'd expect from ordinary crashes (a single worker crash gives count 2).
- Whether to wait before each retry (a delay or backoff), so a failing job doesn't hammer the workers.

### 10.6 Quick recap
- Poison message = the job is the problem, every worker that touches it fails.
- Symptom: delivery count keeps climbing, entry never leaves the PEL.
- Redis will not stop it for you. You must check the delivery count and move the job to a dead-letter stream.
- Don't mix it up with a too-low threshold, which looks the same in `XPENDING` but is not the job's fault.
