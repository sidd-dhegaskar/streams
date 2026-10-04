# Redis Streams: Consumer Groups

Think of a consumer group as a shared work queue built on top of a Redis Stream.

There are two separate concepts:

- **The stream** → stores all jobs permanently.
- **The consumer group** → decides which worker gets which job.

## 1. Without a consumer group

Suppose the stream contains:

```
jobs
├── 1 → job A
├── 2 → job B
├── 3 → job C
├── 4 → job D
```

If w1 reads:

```
XREAD STREAMS jobs 0
```

it sees `A B C D`. Then w2 does the same:

```
XREAD STREAMS jobs 0
```

It also sees `A B C D`.

So normal `XREAD` is essentially: *"Show me what's in the stream."* It doesn't coordinate workers.

## 2. Consumer group changes the model

Now create:

```
XGROUP CREATE jobs workers 0
```

You now have:

```
                    Redis Stream
                  ┌───────────────┐
                  │ A │ B │ C │ D │
                  └───────┬───────┘
                          │
                    Consumer Group
                       "workers"
                          │
                    shared progress
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
                w1                w2
```

The group maintains a shared position in the stream.

```
A   B   C   D
        ↑
   group position
```

When a worker asks for new work, Redis gives it something after that position and advances the group's state.

## 3. Why are they called competing consumers?

Suppose:

```
jobs:
A B C D E F
```

And you have:

```
workers group
├── w1
└── w2
```

They both ask:

```
XREADGROUP GROUP workers w1 ... >
XREADGROUP GROUP workers w2 ... >
```

Redis might distribute the jobs like:

```
A → w1
B → w2
C → w1
D → w2
E → w1
F → w2
```

The important thing: **a job delivered to w1 isn't also delivered to w2 within the same consumer group.** That's the purpose of the group.

So instead of:

```
A → w1
A → w2
A → w3
```

you get:

```
A → w1
B → w2
C → w3
```

This is why they're competing consumers.

## 4. What does `>` mean?

This is probably the most important part of the command:

```
XREADGROUP GROUP workers w1 COUNT 1 STREAMS jobs >
```

The `>` means: *"Give me messages that have never been delivered to a consumer in this group."*

Imagine:

```
jobs:

A   B   C   D   E
↑
```

w1 asks for new messages (`>`). Redis gives `A`. Now A has been delivered to w1.

Then w2 asks for `>`. Redis doesn't give A again. It gives `B`.

```
A → w1
B → w2
```

## 5. What happens if w1 crashes?

This is where Redis Streams become more interesting.

Suppose:

```
A → w1
B → w2
C → w1
```

Redis remembers that:

```
A → w1
C → w1
B → w2
```

These aren't simply forgotten after delivery. They go into the group's **Pending Entries List (PEL)**.

Conceptually:

```
Consumer group: workers

Pending:
A → w1
B → w2
C → w1
```

So Redis knows: *"I gave A and C to w1, but they haven't necessarily been acknowledged yet."*

That's what enables reliable processing.

Later you'll use `XACK` to tell Redis: *"I successfully processed this job."*

```
XACK jobs workers <id>
```

Then Redis removes that entry from the pending list.

## 6. Kafka analogy

Kafka:

```
Topic
  ↓
Partition
  ↓
Consumer Group
  ↓
Consumers
```

Redis Streams:

```
Stream
  ↓
Consumer Group
  ↓
Consumers
```

A useful mental model:

| Kafka                | Redis Streams                                  |
| -------------------- | ---------------------------------------------- |
| Topic                | Stream                                         |
| Consumer group       | Consumer group                                 |
| Consumer             | Consumer                                       |
| Offset               | Group's last-delivered position                |
| Commit offset        | `XACK` / pending tracking concept              |
| Partition assignment | Redis distributes stream entries among consumers |

But don't treat them as identical internally. Redis Streams don't have Kafka's partition model. A Redis Stream is one ordered stream, and the consumer group tracks delivery/pending state for consumers.

## The mental model to keep

Imagine a restaurant:

```
                    JOB STREAM
              ┌────────────────────┐
              │ A B C D E F G H    │
              └─────────┬──────────┘
                        │
                 CONSUMER GROUP
                   "workers"
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
           worker1              worker2
             │                     │
           A, C, E               B, D, F
```

- The stream stores the jobs.
- The consumer group coordinates workers.
- The consumer name identifies which worker received a job.
- The `>` asks for new/unassigned jobs.
- The pending list remembers jobs that were delivered but not acknowledged.
- `XACK` eventually says: *"I finished this job."*

## The progression

```
Step 1
Producer → Stream
             ↓
          jobs stay

Step 2
Consumer → reads stream
             ↓
        reading ≠ deleting

Step 3
Consumer Group
             ↓
       workers share jobs
             ↓
       A → w1
       B → w2
       C → w1

Step 4
Acknowledgement
             ↓
       XACK after processing
             ↓
       reliable processing
```

Step 3 is essentially teaching you how to turn a Redis Stream from "a log that workers can read" into "a shared work queue for multiple workers."

---

# `$` vs `0` vs `>` (where the group starts)

`$` is about where the consumer group starts reading from. It has nothing to do with the PEL or a DLQ.

When you create the group:

```
XGROUP CREATE jobs workers $
```

`$` means: *start the group at the current end of the stream.*

## Example

Suppose the stream already contains:

```
A  B  C  D
```

You create:

```
XGROUP CREATE jobs workers $
```

The group says: *"Okay, I've positioned myself at the end."*

```
A  B  C  D
         ↑
       group position
```

So `A B C D` are not considered new for this group.

If you then add `E` and `F`, consumers using:

```
XREADGROUP GROUP workers w1 STREAMS jobs >
```

receive `E` and `F`.

## Compare `0` vs `$`

```
XGROUP CREATE jobs workers 0
```

Start from the beginning → existing messages are available.

```
XGROUP CREATE jobs workers $
```

Start from the end → only future messages are available.

```
Stream:       A B C D | E F G
              ↑       ↑
             0        $

0 → A B C D E F G
$ →             E F G
```

More precisely, `$` captures the stream's current last ID at group creation time. Messages added afterward become eligible for `>`.

## `>` is different

| Symbol | Meaning |
| ------ | ------- |
| `$`    | Where the consumer group **starts** |
| `>`    | When reading, give me new entries that haven't been delivered to this group |
| PEL    | Tracks entries that were delivered but haven't been acknowledged |

## The flow

```
XGROUP CREATE jobs workers $
                 │
                 ▼
        group starts at end
                 │
                 ▼
       new job gets added
                 │
                 ▼
XREADGROUP ... >
                 │
                 ▼
        worker receives it
                 │
                 ▼
              PEL
                 │
              XACK
                 ▼
          removed from PEL
```
