# Project 5: Streams-Based Job Queue

Consumer groups, PEL, `XCLAIM`, at-least-once delivery. Directly comparable to a Kafka consumer-group project if you've done one.

## Why This Project

Where Redis stops looking like a cache and starts looking like a messaging system. Streams are an append-only log (like a Kafka topic) rather than fire-and-forget. Consumer groups give competing-consumers semantics via a per-group pending-entries list, directly analogous to Kafka consumer group offsets. Simulate a worker crash — the message sits unacknowledged in the PEL until another consumer `XCLAIM`s it after an idle timeout — and be able to explain why that's at-least-once delivery, not exactly-once.

## Build Steps

1. Implement a job queue on a Redis Stream with `XADD`.
2. Set up a consumer group with `XREADGROUP` and competing consumers.
3. Simulate a worker crash mid-processing (don't `XACK`).
4. Show the message sitting unacknowledged in the pending-entries list (PEL).
5. Have another consumer `XCLAIM` it after an idle timeout.
6. Articulate why this is at-least-once delivery, not exactly-once.

## Resources

Runs on a single `redis:7-alpine` container. This is one of the two heaviest lifts in the plan — consumer-group failure semantics take deliberate testing to see.

---
