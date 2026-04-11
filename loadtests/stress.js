import { sleep } from "k6";
import { runMixedScenario, setupContext } from "./common.js";

export const options = {
  stages: [
    { duration: "30s", target: 400 },
    { duration: "60s", target: 1000 },
    { duration: "90s", target: 3000 },
    { duration: "120s", target: 5000 },
    { duration: "60s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<5000"],
    http_req_failed: ["rate<0.45"],
  },
};

export function setup() {
  return setupContext();
}

export default function (data) {
  runMixedScenario(data);
  sleep(0.1);
}
