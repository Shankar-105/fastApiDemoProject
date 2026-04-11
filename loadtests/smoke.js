import { sleep } from "k6";
import { runMixedScenario, setupContext } from "./common.js";

export const options = {
  stages: [
    { duration: "20s", target: 20 },
    { duration: "60s", target: 120 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<1800"],
    http_req_failed: ["rate<0.20"],
  },
};

export function setup() {
  return setupContext();
}

export default function (data) {
  runMixedScenario(data);
  sleep(0.8);
}
