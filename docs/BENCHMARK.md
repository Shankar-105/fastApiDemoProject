# 📸 Benchmark and Deployed Reality

> **_This file is the benchmark proof for the deployed app_**.

## 🎯 Why This File Exists

I wanted a separate benchmark-proof page so anyone reading the project can quickly understand:

1. what the deployed URL can handle,
2. why load and stress fail on current Azure infra,
3. and why this does not mean the backend code is bad.

## 🌐 Target Used for Deployed Benchmark

- Deployed URL: https://fastapi-social-vm.centralindia.cloudapp.azure.com

## 🖼️ Grafana Panels while Smoke Testing

### 1) Requests Per Second and P95 Latency (Deployed)

![Requests Per Second and P95 Latency (Deployed)](../loadtests/results/rpsAndP95.png)

Captured on: 2026-04-12 (deployed smoke-test window)

### 2) Top Slow Endpoints (Deployed)

![Top Slow Endpoints (Deployed)](../loadtests/results/topSlow.png)

Captured on: 2026-04-12 (deployed smoke-test window)

## ✅ Smoke Test Summary (Deployed, Real Run)

Command used:

```powershell
k6 run loadtests/smoke.js
```

Summary from the deployed run as of (2026-04-12):

1. `http_reqs`: `9321` total (`66.28 req/s`)
2. `http_req_failed`: `2.00%` (`187 out of 9321`)
3. `iterations`: `747`
4. `interrupted iterations`: `97`
5. `p95 latency`: `45.07ms` (threshold `p(95)<1800` passed)
6. endpoint checks: `97.99%` passed (`9134/9321`)

Important context from the same run: repeated transport failures still appeared (`request timeout`, connection attempts failing to respond).

> **Note on variance**: _chart values and summary values can vary slightly between runs, and that is expected_.

## ❌ Load Test Summary (Deployed, Real Run) as of 2026-04-12

1. `http_reqs`: `30475` total (`86.66 req/s`)
2. `http_req_failed`: `33.59%` (`10239 out of 30475`)
3. `iterations`: `2242`
4. `interrupted iterations`: `592`
5. `p95 latency`: `58.91s` (threshold failure)
6. repeated transport errors: `request timeout`, `EOF`, `connection reset`, `connect timeout`

## ⛔ Stress Test Note

No separate stress benchmark is required right now for conclusions.
The load profile is already failing hard on deployed infra, so stress will only amplify the same saturation pattern.


## 🧪 Benchmark Summary

From the above smoke,load test runs and the above screenshots, the app currently behaves like this on the current Azure setup:

1. smoke traffic can run in a limited band, but already shows transport instability,
2. load test degrade heavily,
3. p95 and failure rate rise sharply,
4. transport-level failures appear (`timeout`, `EOF`, connection resets, connection attempts failing).

**This is a loud and clear infrastructure saturation signal, not a "weak code" signal.**
**The backend architecture is async and solid; the current Azure VM/DB sizing is what is being overrun under sustained concurrency.**

> **Update After (PR #31):** The app shows measurable improvements after the improvments made in PR #31 but no matter what changes it completely depends on the app infra.

### 🧠 Why is the deployed VM failing even on medium concurrency ?

When localhost with 2 workers achieves **2,183.95 req/s** with a **540ms p95 latency**, why does the deployed VM struggle to handle even **500 rps**?

The answer lies in **single-machine consolidation**. As you can see the Azure infra from [`AZURE_DEPLOYMENT.md`](./AZURE_DEPLOYMENT.md), the deployed setup is resource-constrained:

**Architecture breakdown:**
- **VM Size:** `Standard_B2ats_v2` (burstable, shared CPU with limited sustained performance)
- **Shared Services on One Machine:**
  -  **Nginx** — Reverse proxy + HTTPS termination
  -  **Gunicorn + Uvicorn workers** — FastAPI application
  -  **PostgreSQL** — Database server (shared I/O)
  -  **Redis** — Cache & session store
  -  **RabbitMQ** — Message broker for Celery tasks
  -  **Celery Worker** — Background job processor
  -  **Celery Beat** — Periodic task scheduler

**Under sustained load:**
- All services compete for **limited CPU, memory, and I/O bandwidth**
- Context switching overhead multiplies with more processes
- Database locks and I/O contention spike
- Network buffers fill up, causing backpressure
- Combined load rapidly saturates the VM

**Result:** Transport-level failures (`timeout`, `EOF`, `connection reset`) and request queueing appear—not due to code quality, but **infrastructure saturation**.

## ✅ Honest Conclusion

**_The async backend architecture is solid look [`App Performance Result`](./MONITORING_AND_LOAD_TESTING.md#-performance-results-on-different-worker-counts) and is expected to scale much higher on stronger infra tiers and better resource separation._**