# 📊 Monitoring and Load Testing

> This is performance room: generate traffic with k6, inspect metrics in Prometheus, and read live behavior in Grafana.

>You will also see the comparsion of local vs deployed runs in depth

This is also a good path way for new contributors who open the repo and want to understand:

1. what observability tools are used here,
2. how to run the stack,
3. how to run smoke, load, and stress tests,
4. and how to read results when things go good or bad.

You do not need to manually wire Prometheus or Grafana. They are already configured in Docker Compose for this project.

## ✅ Before You Start

1. Complete the project setup from [docs/SETUP.md](docs/SETUP.md).
2. Start the stack with Docker Compose.
3. Install k6 separately on your machine (k6 is not currently packaged inside this repo Docker Compose stack).

Important:

1. Prometheus and Grafana are optional for running k6.
2. k6 can run against any reachable base URL even if Prometheus or Grafana are down.
3. Prometheus and Grafana help you observe behavior, but they are not required for traffic generation.

## 🚀 Run Everything

### 1) Start services

```powershell
docker compose up -d
```

Useful URLs after startup:

1. API health: http://localhost:8000/health
2. Prometheus: http://localhost:9090
3. Grafana: http://localhost:3000

Tip:

1. Prometheus and Grafana are for observing behavior.
2. k6 still works even if those two are down, as long as your API target URL is reachable.

## 🖥️ How to Use Grafana and Prometheus After k6

After starting a k6 run, keep Grafana and Prometheus open in browser tabs.

### Grafana walkthrough

1. Open http://localhost:3000 and sign in.
2. Go to Dashboards.
3. Open folder: Observability.
4. Open dashboard: Social API Observability.
5. Watch these panels while load is running:
	1. Requests per second,
	2. p95 latency,
	3. error rate,
	4. 4xx and 5xx counts,
	5. top slow endpoints.

This gives the fastest visual story of how the API behaves under traffic.

### Prometheus walkthrough

1. Open http://localhost:9090.
2. Prometheus is not primarily for pretty charts.
3. It is the metrics database + query UI.
4. Run PromQL queries to inspect raw metric series.

Starter queries:

```promql
up
sum(http_requests_total)
rate(http_requests_total[1m])
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
```

If you want visual dashboards, use Grafana.
If you want direct metric queries/debugging, use Prometheus UI.

## 🌍 Local vs Deployed: Why Deployed Can Look Worse

### 🧪 Local baseline first (recommended)

For local baseline testing:

1. Keep `BASE_URL` in [loadtests/common.js](../loadtests/common.js) pointed to localhost.
2. Run:

```powershell
k6 run loadtests/load.js
```

> After k6 finishes, **the app now (2026-05-09) sustains roughly 1k req/sec with near-zero transport failures and 0% request failure** rate on that run, even with a **single Uvicorn process**. That is a strong baseline.

### ✅ Local run snapshot (real output) as of 2026-05-09

Local `k6 run loadtests/load.js` summary from this project:

1. `http_reqs`: `301188` total (`1004.56 req/s`)
2. `http_req_failed`: `0.00%` (`0 out of 301188`)
3. `iterations`: `25097`
4. `interrupted iterations`: `0`
5. `p95 latency`: `2.18s` (threshold `p(95)<2500` safely passed)
6. endpoint checks: `100%` passed (`301188/301188`)

> _even with one Uvicorn process in the local path, the app now sustains roughly 1k req/s with stable success behavior and no transport failures_.

### ☁️ Now run the same test against deployed URL

After local baseline, run the exact same test for deployed app.

1. In [loadtests/common.js](../loadtests/common.js), set `BASE_URL` to:

```javascript
https://fastapi-social-vm.centralindia.cloudapp.azure.com
```

2. Run the same command:

```powershell
k6 run loadtests/load.js
```

> **At first glance**, you may expect more throughput because deployment uses **_Gunicorn + 2 Uvicorn workers_**, **so it feels like it should do maybe close to 1000 req/sec or even more**.

In real runs, it performs **worse than local**.

### ❌ Deployed run snapshot (real output) as of 2026-05-09

Deployed `k6 run loadtests/load.js` summary from this project:

1. `http_reqs`: `38996` total (`112.43 req/s`)
2. `http_req_failed`: `12.84%` (`5007 out of 38996`)
3. `iterations`: `3128`
4. `interrupted iterations`: `141`
5. `p95 latency`: `9.84s` (threshold still failing, but much better than the original saturation run)
6. repeated transport errors: `request timeout`, `EOF`, `connect timeout`

### 🧠 Why deployed VM can be worse than local even with 2 workers

Two workers are not enough by themselves; worker count is only one layer, and the real throughput comes from the full end-to-end path: Nginx, Gunicorn/Uvicorn worker behavior, app code and query shape, Redis, Postgres over network, and Azure infrastructure limits. Localhost mostly shows raw app and query-path performance because it removes TLS, public network latency, and most VM contention, while the deployed path adds all of that plus the possibility of CPU, memory, and I/O pressure in the shared VM/DB stack.

If you check [docs/AZURE_DEPLOYMENT.md](./AZURE_DEPLOYMENT.md), the deployed profile is resource-constrained for heavy sustained traffic.
What this means under load:

1. Burstable VM can throttle when CPU credits drain,
2. remote DB latency and IOPS limits dominate at high concurrency,
3. this k6 script is heavy per iteration (many endpoints each loop),
4. Nginx/Gunicorn backlog and timeout behavior can amplify drops,
5. TLS + public internet overhead exists in the deployed path but not localhost,
6. a stronger cloud layout can still scale much further because the app code is now much closer to its raw limit.

That is why you can see timeout/EOF/connect errors and lower req/s in deployed runs even when worker count appears better on paper.

### 📌 Final Takeaway

Local and cloud benchmarks measure two complementary truths about system health. Local runs expose raw application and query-path performance — they show how efficiently your code, ORM shape, and database interactions behave without TLS, public network latency, or VM contention. A strong local baseline (for example, ~1k req/s) is a clear signal that the implementation and query paths are efficient.

Cloud runs measure end-to-end, real-world capacity: networking, TLS, VM sizing, managed DB/Redis tiers, and operational headroom. Lower deployed numbers typically point to infrastructure limits to be addressed (CPU/memory/IO/DB latency, network/TLS overhead), not a failure of the application design.

Both views are valuable and complementary: use the local baseline to validate and iterate on queries, caching, and code paths, then use cloud benchmarks to size and tune infrastructure so the app can serve real users at scale.