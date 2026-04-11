import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 2,
  duration: "45s",
  thresholds: {
    http_req_duration: ["p(95)<1500"],
    http_req_failed: ["rate<0.30"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

function hitHealth() {
  const res = http.get(`${BASE_URL}/health`, {
    tags: { endpoint: "health" },
  });

  check(res, {
    "health status is 200": (r) => r.status === 200,
  });
}

function hitFeedExplore() {
  const res = http.get(`${BASE_URL}/feed/explore?page=1&limit=10`, {
    tags: { endpoint: "feed_explore" },
  });

  check(res, {
    "feed/explore reachable": (r) => [200, 401, 403].includes(r.status),
  });
}

function hitAuthLogin() {
  const payload = JSON.stringify({
    email: "smoke@example.com",
    password: "wrong-password",
  });

  const params = {
    headers: { "Content-Type": "application/json" },
    tags: { endpoint: "auth_login" },
  };

  const res = http.post(`${BASE_URL}/login`, payload, params);

  check(res, {
    "login endpoint reachable": (r) => [202, 400, 401, 422].includes(r.status),
  });
}

export default function () {
  hitHealth();
  hitFeedExplore();
  hitAuthLogin();
  sleep(1);
}
