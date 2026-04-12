# Monitoring and Load Testing

This guide is for new contributors who open the repo and want to understand:

1. what observability tools are used here,
2. how to run the stack,
3. how to run smoke, load, and stress tests,
4. and how to read results when things go good or bad.

You do not need to manually wire Prometheus or Grafana. They are already configured in Docker Compose for this project.

## Before You Start

1. Complete the project setup from [docs/SETUP.md](docs/SETUP.md).
2. Start the stack with Docker Compose.
3. Install k6 separately on your machine (k6 is not currently packaged inside this repo Docker Compose stack).

Important:

1. Prometheus and Grafana are optional for running k6.
2. k6 can run against any reachable base URL even if Prometheus or Grafana are down.
3. Prometheus and Grafana help you observe behavior, but they are not required for traffic generation.

## Quick Tool Primer

### OpenTelemetry (OTel)

OTel gives traces. Think of traces as a per-request timeline.

It helps answer:

1. which part of the request was slow,
2. which operation happened before failure,
3. where latency is accumulating.

### Prometheus

Prometheus stores numeric time-series metrics.

It helps answer:

1. requests per second,
2. p95 latency trend,
3. error percentage trend,
4. per-endpoint load patterns.

### Grafana

Grafana visualizes Prometheus metrics in dashboards.

It helps answer:

1. is the system healthy right now,
2. which route is becoming slow,
3. whether errors are 4xx or 5xx driven.

### k6

k6 is the traffic generator. It sends synthetic user traffic to your app.

It helps answer:

1. how the app behaves under increasing concurrency,
2. when p95 starts degrading,
3. when transport-level failures appear (timeouts, EOF, connection resets),
4. where bottlenecks exist in app or infrastructure.

## What Is Already Wired In This Repo

1. Prometheus container and scrape config.
2. Grafana container with datasource and dashboard provisioning.
3. FastAPI metrics endpoint at /metrics.
4. FastAPI tracing instrumentation.
5. k6 scripts:
	1. [loadtests/smoke.js](../loadtests/smoke.js)
	2. [loadtests/load.js](../loadtests/load.js)
	3. [loadtests/stress.js](../loadtests/stress.js)
	4. [loadtests/common.js](../loadtests/common.js)

## Run Everything

### 1) Start services

```powershell
docker compose up -d
```

Useful URLs after startup:

1. API health: http://localhost:8000/health
2. Prometheus: http://localhost:9090
3. Grafana: http://localhost:3000

### 2) Run k6 tests

Smoke:

```powershell
k6 run -e BASE_URL=http://localhost:8000 loadtests/smoke.js
```

Load:

```powershell
k6 run -e BASE_URL=http://localhost:8000 loadtests/load.js
```

Stress:

```powershell
k6 run -e BASE_URL=http://localhost:8000 loadtests/stress.js
```

To test deployed target instead of local:

```powershell
k6 run -e BASE_URL=https://fastapi-social-vm.centralindia.cloudapp.azure.com loadtests/load.js
```

## How to Read k6 Output

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

## Local vs Deployed: Why Deployed Can Look Worse

It is common for a deployed environment to underperform local if infrastructure is constrained.

Typical reasons:

1. VM size limits (CPU, memory, burst credits),
2. managed DB tier limits (CPU and IOPS),
3. network latency to database,
4. reverse proxy and worker queue saturation,
5. TLS and internet path overhead,
6. limited worker count relative to workload shape.

So two workers alone do not guarantee higher throughput.

## Suggested Workflow for New Contributors

1. Start with smoke test.
2. Move to load test.
3. Observe p95 trend and error rate.
4. Run stress test only after load baseline is understood.
5. Compare local and deployed with the same script and explicit BASE_URL.

## Final Notes

1. This guide focuses on practical, reproducible testing.
2. k6 generates traffic, Prometheus stores metrics, Grafana visualizes metrics, and OTel gives request-level trace context.
3. Use all four together for fastest root-cause analysis.