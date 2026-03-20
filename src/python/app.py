from flask import Flask, request, jsonify
import os, subprocess, time
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime

app = Flask(__name__)

header = {"X-Mode" : os.getenv("MODE")}
start_time = time.time()


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Welcome to SwiftDeploy CLI",
        "current_mode": os.getenv("MODE"),
        "version": os.getenv("VERSION"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200, header

@app.route('/healthz', methods=['GET'])
def healthz():
    uptime = time.time() - start_time
    return jsonify({
        "status": "healthy",
        "uptime": round(uptime, 2),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200, header

@app.route('/metrics', methods=['GET'])
# def metrics():

@app.route('/chaos', methods=['POST'])
def chaos():
    data = request.get_json()
    mode = data.get('mode')
    duration = data.get('duration', 0)
    rate = data.get("rate")

    if os.getenv("MODE") != "canary":
        return jsonify({
            "error": "Chaos testing is only allowed in canary mode"
        }), 403, header
    
    if mode == "slow": 
        time.sleep(duration/1000)
        return jsonify({
            "message": f"Simulated slow response for {duration} ms"
        }), 200, header
    
    if mode == "error":
        return jsonify({
            "message": f"Simulated error response with rate {rate}%"
        }), 500, header
    
    if mode == "recover":
        return jsonify({
            "message": "Recovered from chaos testing"
        }), 200, header
    


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv("PORT")))
