import { sleep } from "k6";
import { runMixedScenario, setupContext } from "./common.js";

export const options = {
  stages: [
    { duration: "30s", target: 200 },
    { duration: "90s", target: 700 },
    { duration: "120s", target: 1000 },
    { duration: "60s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<2500"],
    http_req_failed: ["rate<0.30"],
  },
};

export function setup() {
  return setupContext();
}

export default function (data) {
  runMixedScenario(data);
  sleep(0.35);
}
