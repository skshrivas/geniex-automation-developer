# Q3 — Predict the Failure

The CapSolver API goes down at **14:00 UTC**. Every call to `CaptchaSolver.solve_turnstile()` raises `CaptchaProviderError("503 Service Unavailable")`.

At this moment, Campaign **C-001** has just dispatched its first worker, which is beginning to process job **J-001**. J-001 has no session cookies and no `cf_clearance` — it is a fresh job.

---

**(a)**

Trace what happens to J-001 from its first CAPTCHA solve attempt through to its final status.

- How many times does `captcha_solves_used` increment?
- Read `worker._solve_captcha()` carefully — what does it return when `CaptchaProviderError` is raised?
- Read `worker._process_job()` — what path does execution take after `_solve_captcha` returns?
- What is J-001's final `status`?

---

**(b)**

The CapSolver API comes back online at **14:10 UTC**. C-001's operator checks the dashboard.

- What status do J-001 through J-005 show?
- Is there an automatic code path that would retry these jobs? Trace through `worker.py` and `campaign.py` to support your answer.
- What action would the operator need to take to get this data collected?

---

**(c)**

Consider two scenarios that both result in jobs reaching `EXHAUSTED` status:

**Scenario A**: The CAPTCHA provider was down for 10 minutes (infrastructure failure). Proxies and accounts are healthy.

**Scenario B**: The target site has blocked your entire proxy range. Every solve attempt returns a valid token, but every request returns `403`. Each token attempt is counted, and eventually the budget is exhausted.

From the data stored in `models.py` and `campaign.py` — the fields on `Job`, `JobResult`, and `Campaign` — how would an operator distinguish between these two scenarios after the fact?

What fields, if any, would be different between the EXHAUSTED jobs in Scenario A vs. Scenario B?
