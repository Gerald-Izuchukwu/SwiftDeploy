from flask import Flask, request, jsonify, Response
import os, time, random, threading
from dotenv import load_dotenv
from datetime import datetime
from prometheus_client import Gauge, Histogram, Counter, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST

load_dotenv()

app = Flask(__name__)

MODE = os.getenv("MODE", "stable")       
VERSION = os.getenv("VERSION", "1.0.0")
PORT = int(os.getenv("PORT", 3000))
START_TIME = time.time()

# ── Chaos State ───────────────────────────────────────────────────────────────
chaosState = {"mode": "none", "rate": 0.0, "duration": 0}
chaosLock = threading.Lock()              
# ── Prometheus Metrics ────────────────────────────────────────────────────────
register = CollectorRegistry()            

httpRequestsTotal = Counter(
    "http_requests_total",
    "Total HTTP requests served",
    ["method", "path", "status_code"],
    registry=register                     
)

httpRequestDuration = Histogram(
    "http_request_duration_seconds",
    "Request latency histogram",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    registry=register
)

appUptime = Gauge(                        
    "app_uptime_seconds",
    "Seconds since process start",
    registry=register
)

appMode = Gauge(
    "app_mode",
    "App mode: 0=stable, 1=canary",
    registry=register
)
appMode.set(1 if MODE == "canary" else 0)

chaosActive = Gauge(
    "chaos_active",
    "Chaos state: 0=none, 1=slow, 2=error",
    registry=register
)
chaosActive.set(0)

# ── Middleware ────────────────────────────────────────────────────────────────
@app.before_request
def before_request():
    request._start_time = time.time()     # store start time on request object

@app.after_request
def after_request(response):
    duration = time.time() - request._start_time
    httpRequestDuration.observe(duration)
    httpRequestsTotal.labels(
        method=request.method,
        path=request.path, 
        status_code=str(response.status_code)
    ).inc()
    appUptime.set(time.time() - START_TIME)
    response.headers["X-Mode"] = MODE    # add header to every response here
    return response                       # must return response

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    with chaosLock:
        current_chaos = chaosState.copy()

    if current_chaos["mode"] == "slow":
        time.sleep(current_chaos["duration"])   # duration is in seconds

    elif current_chaos["mode"] == "error" and random.random() < current_chaos["rate"]:
        return jsonify({"error": "chaos induced error"}), 500

    return jsonify({
        "message": "Welcome to SwiftDeploy CLI",
        "current_mode": MODE,
        "version": VERSION,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({
        "status": "ok",
        "uptime": round(time.time() - START_TIME, 2),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    appUptime.set(time.time() - START_TIME)   # update right before scraping
    data = generate_latest(register)           # generate Prometheus text format
    return Response(data, mimetype=CONTENT_TYPE_LATEST)


@app.route("/chaos", methods=["POST"])
def chaos():
    if MODE != "canary":
        return jsonify({"error": "chaos only available in canary mode"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "request body required"}), 400

    mode = data.get("mode")
    duration = data.get("duration", 5)
    rate = data.get("rate", 0.5)

    with chaosLock:                            # lock when writing shared state
        if mode == "slow":
            chaosState.update({"mode": "slow", "duration": duration, "rate": 0})
            chaosActive.set(1)
            return jsonify({"chaos": "slow", "duration": duration}), 200

        elif mode == "error":
            chaosState.update({"mode": "error", "rate": rate, "duration": 0})
            chaosActive.set(2)
            return jsonify({"chaos": "error", "rate": rate}), 200

        elif mode == "recover":
            chaosState.update({"mode": "none", "rate": 0.0, "duration": 0})
            chaosActive.set(0)
            return jsonify({"chaos": "recovered"}), 200

        else:
            return jsonify({"error": "invalid chaos mode"}), 400


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=PORT)