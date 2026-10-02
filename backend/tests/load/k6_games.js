import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";
import ws from "k6/ws";

const baseUrl = __ENV.BASE_URL || "http://localhost:8000";
const wsUrl = (__ENV.WS_URL || baseUrl.replace(/^http/, "ws")) + "/ws/games/aviator";
const users = Number(__ENV.USERS || 100);
const fanoutLatency = new Trend("ws_fanout_latency", true);
const wsErrors = new Rate("ws_error_rate");

export const options = {
  vus: users,
  duration: __ENV.DURATION || "2m",
  thresholds: {
    http_req_duration: ["p(95)<300"],
    http_req_failed: ["rate<0.01"],
    ws_fanout_latency: ["p(95)<500"],
    ws_error_rate: ["rate<0.01"],
  },
};

export default function () {
  const response = http.get(`${baseUrl}/api/v1/games`);
  check(response, {
    "game catalog returned 200": (r) => r.status === 200,
  });

  const connected = ws.connect(wsUrl, {}, function (socket) {
    socket.on("message", (message) => {
      try {
        const event = JSON.parse(message);
        const eventTime = event.ts || event.timestamp;
        if (eventTime && event.type !== "CONNECTED" && event.type !== "STATE_SNAPSHOT") {
          fanoutLatency.add(Math.max(0, Date.now() - Date.parse(eventTime)));
        }
      } catch (_) {
        wsErrors.add(1);
      }
    });
    socket.on("error", () => wsErrors.add(1));
    socket.setTimeout(() => socket.close(), 15000);
  });
  check(connected, { "WebSocket handshake returned 101": (r) => r && r.status === 101 });
  sleep(1);
}
