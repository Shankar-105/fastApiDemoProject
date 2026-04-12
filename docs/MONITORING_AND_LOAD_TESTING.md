# 📊 Monitoring and Load Testing

This guide is for new contributors who open the repo and want to understand:

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

## 🧩 Quick Tool Primer

### 🔎 OpenTelemetry (OTel)

OTel gives traces. Think of traces as a per-request timeline.

It helps answer:

1. which part of the request was slow,
2. which operation happened before failure,
3. where latency is accumulating.

### 🗄️ Prometheus

Prometheus stores numeric time-series metrics.

It helps answer:

1. requests per second,
2. p95 latency trend,
3. error percentage trend,
4. per-endpoint load patterns.

Think of Prometheus UI like a query console for metrics data.
It is similar in spirit to tools like pgAdmin where you query a database, except here you query time-series metrics (TSDB) with PromQL.

### 📈 Grafana

Grafana visualizes Prometheus metrics in dashboards.

It helps answer:

1. is the system healthy right now,
2. which route is becoming slow,
3. whether errors are 4xx or 5xx driven.

Prometheus stores and serves the data.
Grafana is the visualization layer that turns those queries into charts.

### ⚡ k6

k6 is the traffic generator. It sends synthetic user traffic to your app.

It helps answer:

1. how the app behaves under increasing concurrency,
2. when p95 starts degrading,
3. when transport-level failures appear (timeouts, EOF, connection resets),
4. where bottlenecks exist in app or infrastructure.

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

## 📌 How to Read k6 Output

The most important lines are:

1. http_req_duration with p95
2. http_req_failed rate
3. iterations complete and interrupted
4. endpoint checks pass or fail

Example interpretation:

1. If p95 crosses threshold but failures are near zero:
	1. system is still serving requests,
	2. but latency tail is getting too slow.
2. If p95 and failure rate both spike:
	1. system is overloaded,
	2. queueing and transport failures are happening.
3. If interrupted iterations increase:
	1. many VUs were still in progress when test stopped,
	2. usually a sign of long-running or stuck requests under pressure.

## 🌍 Local vs Deployed: Why Deployed Can Look Worse

### 🧪 Local baseline first (recommended)

For local baseline testing:

1. Keep `BASE_URL` in [loadtests/common.js](../loadtests/common.js) pointed to localhost.
2. Run:

```powershell
k6 run loadtests/load.js
```

From our recent local baseline, the app sustained roughly 500+ req/s with near-zero transport failures and 0% request failure rate on that run, even with a single Uvicorn process. That is a strong baseline.

### ✅ Local run snapshot (real output)

Local `k6 run loadtests/load.js` summary from this project:

1. `http_reqs`: `141339` total (`468.37 req/s`)
2. `http_req_failed`: `0.00%` (`0 out of 141339`)
3. `iterations`: `11778`
4. `interrupted iterations`: `0`
5. `p95 latency`: `2.71s` (threshold `p(95)<2500` narrowly crossed)
6. endpoint checks: `100%` passed (`141339/141339`)

Confidence signal: even with one Uvicorn process in local path, the app handled high throughput with stable success behavior.

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

At first glance, you may expect more throughput because deployment uses Gunicorn + 2 Uvicorn workers, so it feels like it should do maybe close to 1000 req/s.

In real runs, it can still perform worse than local.

### ❌ Deployed run snapshot (real output)

Deployed `k6 run loadtests/load.js` summary from this project:

1. `http_reqs`: `30475` total (`86.66 req/s`)
2. `http_req_failed`: `33.59%` (`10239 out of 30475`)
3. `iterations`: `2242`
4. `interrupted iterations`: `592`
5. `p95 latency`: `58.91s` (threshold failure)
6. repeated transport errors: `request timeout`, `EOF`, `connection reset`, `connect timeout`

Confidence signal: this is not a tiny variance. It is a clear saturation pattern difference between local and deployed path.

### 🧠 Why deployed VM can be worse than local even with 2 workers

Two workers are not enough by themselves.
Worker count is only one layer.

Real throughput depends on the full end-to-end path:

1. Nginx,
2. Gunicorn/Uvicorn worker behavior,
3. app code and query shape,
4. Redis,
5. Postgres over network,
6. Azure infrastructure limits.

If you check [docs/AZURE_DEPLOYMENT.md](./AZURE_DEPLOYMENT.md), the deployed profile is resource-constrained for heavy sustained traffic:

1. VM: `Standard_B2ats_v2` (burstable class),
2. Postgres: `B1ms` tier (small tier),
3. Redis runs on same VM and competes for CPU/RAM with app and Nginx.

What this means under load:

1. Burstable VM can throttle when CPU credits drain,
2. remote DB latency and IOPS limits dominate at high concurrency,
3. this k6 script is heavy per iteration (many endpoints each loop),
4. Nginx/Gunicorn backlog and timeout behavior can amplify drops,
5. TLS + public internet overhead exists in deployed path but not localhost.

That is why you can see timeout/EOF/connect errors and lower req/s in deployed runs even when worker count appears better on paper.

### 📉 Failure pattern you usually see when deployed starts saturating

1. p95 rises sharply,
2. request timeouts and EOF increase,
3. interrupted iterations increase,
4. overall req/s flattens or drops.

### 📌 Quick takeaway

Workers increase app capacity, but they do not remove infrastructure bottlenecks.
If DB, VM, or network saturates first, p95 latency and timeout/EOF failures will rise even when worker count looks "better" on paper.

## 📝 Final Notes

1. This guide focuses on practical, reproducible testing.
2. k6 generates traffic, Prometheus stores metrics, Grafana visualizes metrics, and OTel gives request-level trace context.
3. Use all four together for fastest root-cause analysis.