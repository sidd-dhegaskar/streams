import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

def enqueue(job_number):
    entry_id = r.xadd("jobs", {"task": "resize", "file": "a.txt", "job_number": job_number})
    return entry_id

for i in range(10):
    print(enqueue(i))
