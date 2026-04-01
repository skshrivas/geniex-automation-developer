# Q2 — Trace the Session

Campaign **C-001** has 5 pending jobs and is being started fresh. The worker acquires proxy **P-001** for the first job, **J-001**.

Walk through the following sequence step by step. Reference specific functions and files by name.

---

**Step 1**

`worker._process_job(J-001)` begins, attempt index 0.

`session_manager.get_session_cookies(J-001)` is called — this returns the cookie jar for the account assigned to J-001, which is **ACC-001**.

Look at ACC-001's cookie jar in `seed_jobs.py`. What cookies does it contain? What is the value of `cf_clearance`, and what does the comment in the seed data say about which proxy solved it?

---

**Step 2**

In `worker.py`, the condition `if "cf_clearance" not in cookies` is evaluated.

Is it `True` or `False`? What does the worker do as a result?

---

**Step 3**

The request is sent through **P-001** with the existing `cf_clearance` cookie from ACC-001's jar.

Cloudflare validates `cf_clearance` against the incoming IP. The cookie was solved by **P-003** (see `seed_jobs.py`). What does Cloudflare return — and what HTTP status code does it use?

---

**Step 4**

`http_client.execute()` returns its response. What does `ErrorClassifier.classify()` return for this response? What remediation action does `worker.py` take?

Now: the response body is a Cloudflare JS challenge page — valid HTML, roughly 12 KB. `PriceParser.parse()` is called. What does it return? What does `worker.py` do with `parse_result`?

---

**Step 5**

Fifteen minutes later, P-001's `sticky_until` timestamp has passed (see `seed_jobs.py`).

A second campaign worker starts and calls `proxy_pool.acquire(campaign_id="C-002")`. Read `proxy_pool.acquire()` — what does it return? Why?

---

**Final state**

Describe the state of both campaigns and both workers after step 5. What does the monitoring dashboard show for C-001? For C-002?

What does an operator looking at the dashboard conclude about C-001's first job?
