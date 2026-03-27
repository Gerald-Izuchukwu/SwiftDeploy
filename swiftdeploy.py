import sys, os, subprocess, time, json, socket, yaml, ruamel.yaml, urllib.request
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, UTC

MANIFEST= "manifest.yaml"
METRICS_LOG = ".metrics_history.jsonl"


#1 load the manifest file
def load_manifest():
    with open(MANIFEST) as f:
        # print(yaml.safe_load(f))
        return yaml.safe_load(f)


#2 Load the templates folder and read the templates files
def render_templates(manifest):
    env = Environment(loader=FileSystemLoader("templates"))
    docker_compose = env.get_template("docker-compose.yaml.j2").render(**manifest)
    nginx = env.get_template("nginx.conf.j2").render(**manifest)
    with open("nginx.conf", "w") as f:
        f.write(nginx)
    with open("docker-compose.yaml", "w") as f:
        f.write(docker_compose)

    print("✓ nginx.conf generated")
    print("✓ docker-compose.yml generated")

#3 swift deploy init
def swiftdeploy_init():
    manifest = load_manifest()
    render_templates(manifest)

#4 validate some parameters
def swiftdeploy_validate():
    ok = True
    # first check: if manifest.yaml exists
    if not os.path.exists(MANIFEST):
        print("✗ manifest.yaml does not exist")
        ok = False
    # second check: if manifest.yaml is valid yaml
    try:
        manifest = load_manifest()
        print("✓ manifest.yaml is valid")
    except Exception as e:
        print(f"✗ manifest.yaml is invalid: {e}")
        ok = False
        manifest = {}

    # third check: if manifest.yaml has required fields
    required = ["services.node.name","services.node.image","services.node.port_on_host","nginx.port_on_host","network.name"]
    missing = []
    for field in required:
        keys = field.split(".")
        value = manifest
        for key in keys:
            value = value.get(key, None) if isinstance(value, dict) else None
        if not value:
            missing.append(field)
    if missing:
        print(f"✗ manifest.yaml is missing required fields: {', '.join(missing)}")
        ok = False
    else:
        print("✓ manifest.yaml has all required fields")   

    # fourth check: if image is valid
    image = manifest.get("services", {}).get("node", {}).get("image", "")
    r = subprocess.run(["docker", "pull", image], capture_output=True)
    result = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if result.returncode != 0:
        print(f"✗ Docker image '{image}' does not exist locally or remotely")
        ok = False
    else:
        print(f"✓ Docker image '{image}' is valid")

    #fifth check: if nginx port is available
    port = manifest.get("nginx", {}).get("port_on_host", 80)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(('localhost', int(port))) == 0:
            print(f"✗ Port {port} is already in use on localhost")
            ok = False
        else:
            print(f"✓ Port {port} is available on localhost")
    
    #sixth check: if docker-compose exists
    result = subprocess.run(["docker", "compose", "version"], capture_output=True)
    if result.returncode != 0:
        print(f"✗ Docker compose not installed, please install")
    else:
        print(f"✓ Docker compose is installed")

#5 swiftdeploy deploy
def swiftdeploy_deploy():
    # call init function
    swiftdeploy_init()
    # bring stack up using docker compose up
    print("Starting stack...")
    result = subprocess.run(["docker", "compose", "up", "-d", "--build"], capture_output=True)
    if result.returncode ==0:
        print('✓ Stack is up and running ')
    else:
        print(result)
        print(f"✗ Something is wrong with running docker compose")
    # run health check
    manifest = load_manifest()
    port = manifest["nginx"]["port_on_host"]
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=3)
            print("✓ Stack is healthy")
            return
        except:
            time.sleep(3)
    print("✗ Health check timed out after 60s"); sys.exit(1)

#6 swiftdeploy status
def swiftdeploy_status():
    manifest = load_manifest()
    port = manifest["nginx"]["port_on_host"]
    interval = manifest["metrics"]["scrape_interval"]
    retention = manifest["metrics"]["retention"]
    prev_count = None
    prev_time = None
    while True:
        os.system("clear")
        try:
            raw = urllib.request.urlopen(f"http://localhost:{port}/metrics", timeout=5).read().decode()
            snapshot = parse_metrics(raw)
            snapshot["timestamp"] = datetime.now(UTC).isoformat()
            # Append to history
            with open(METRICS_LOG, "a") as f:
                f.write(json.dumps(snapshot) + "\n")
            #Trim history
            trim_history(retention)
            #compute rate

            rate, prev_count, prev_time = compute_rate(snapshot["total_requests"], prev_count, prev_time)
            uptime_str = format_uptime(snapshot.get('uptime', 0))
            print(f"┌──────────────────── SwiftDeploy Status ────────────────────┐")
            print(f"│ Service : {manifest['services']['name']} ({snapshot.get('mode','?')})  Uptime: {uptime_str} |")
            print(f"│ Requests: {snapshot.get('total_requests',0)} total  Rate: {rate:.1f} req/s |")
            print(f"│ Errors  : {snapshot.get('error_rate',0):.1f}%  Latency avg: {snapshot.get('avg_latency',0)*1000:.0f}ms  p99: {snapshot.get('p99',0)*1000:.0f}ms |")
            print(f"│ Chaos   : {snapshot.get('chaos','none')}  Nginx: ✓ |")
            print(f"└────────────────────────────────────────────────────────────┘")
            print(f"\nRefreshing every {interval}s — Ctrl+C to exit")
        except KeyboardInterrupt:
            print("\nExiting Status View")
            break
        except Exception as e:
            print(f"Error Scraping metrics {e}")
        time.sleep(interval)

# swiftdeploy promote mode
def swiftdeploy_promote(target):
    #first we read and update the manifest with target 
    ry = ruamel.yaml.YAML()
    with open (MANIFEST) as f:
        manifest = ry.load(f)
    manifest["services"]["node"]["MODE"] = target
    with open(MANIFEST, "w") as f:
        ry.dump(manifest, f)

    #next regenerate docker compose
    render_templates(load_manifest())

    #restart on the service container(Nodejs container)
    service = manifest["services"]["node"]["name"]
    subprocess.run(["docker", "compose", "up", "-d", "--force-recreate", "--no-deps", service], check=True)

    # confirm switching
    time.sleep(3)
    port = manifest["nginx"]["port_on_host"]
    response = urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=5).read()
    print(f"Mode switched to {target}. /healthz: {response.decode()}")

# tear down/bring down everything
def swiftdeploy_teardown(clean=False):
    subprocess.run(["docker", "compose", "down"], capture_output=True)
    if clean == True:
        for f in ["nginx.conf", "docker-compose.yaml"]:
            if os.path.exists(f):
                os.remove(f)
        print("Generated Files removed")


def parse_metrics(text):
    result = {
        "total_requests": 0,
        "error_rate": 0,
        "mode": "stable",
        "chaos": "none",
        "uptime": 0,
        "avg_latency": 0,
        "p99": 0
    }
    total = 0
    errprs = 0
    duration_sum = 0
    duration_count = 0
    buckets = {}
        
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        if line.startswith("http_requests_total{"):
            parts = line.split(" ")
            count = float(parts[-1])
            total += count 
            if "status_code=5":
                errors += count
        elif line.startswith("http_request_duration_seconds_bucket{"):
            le = line.split('le="')[1].split('"')[0]
            val = float(line.split()[-1])
            buckets[le] = val
        elif line.startswith("http_request_duration_seconds_count"):
            duration_count = float(line.split()[-1])
        elif line.startswith("app_uptime_seconds"):
            result["uptime"] = float(line.split()[-1])
        elif line.startswith("app_mode"):
            result["mode"] = "canary" if float(line.split()[-1]) == 1 else "stable"
        elif line.startswith("chaos_active"):
            v = float(line.split()[-1])
            result["chaos"] = {0:"none", 1:"slow", 2:"error"}.get(int(v),"none")
            result["total_requests"] = int(total)
    result["error_rate"] = (errors/total*100) if total > 0 else 0
    result["avg_latency"] = (duration_sum/duration_count) if duration_count > 0 else 0
    # p99 from buckets
    if buckets and duration_count > 0:
        target = 0.99 * duration_count
        sorted_buckets = sorted([(float(k) if k != "+Inf" else float("inf"), v) for k,v in buckets.items()])
        for le, count in sorted_buckets:
            if count >= target:
                result["p99"] = le if le != float("inf") else 5.0
                break
    return result

def trim_history(retention):
    if not os.path.exists(METRICS_LOG): return
    with open(METRICS_LOG) as f:
        lines = f.readlines()
    if len(lines) > retention:
        with open(METRICS_LOG, "w") as f:
            f.writelines(lines[-retention:])

def compute_rate(val, prev_count, prev_time):
    rate = 0
    if prev_count is not None and prev_time is not None:
        elapsed = time.time() - prev_time
        rate = (val - prev_count)/ elapsed if elapsed > 0 else 0
    prev_count = val
    prev_time = time.time()
    return rate, prev_count, prev_time

def format_uptime(seconds):
    hour = int(seconds // 3600)
    minute = int((seconds % 3600) // 60)
    second = int(seconds % 60) 
    return f"{hour}h {minute}m {second}s"


if __name__ == "__main__":
    args = sys.argv[1: ]
    if not args:
        print("Usage: swiftdeploy <command> [options]"); sys.exit(1)
    cmd = args[0]
    if cmd == "init": 
        swiftdeploy_init()
    elif cmd == "validate": 
        swiftdeploy_validate()
    elif cmd == "deploy": 
        swiftdeploy_deploy()
    elif cmd == "status": 
        swiftdeploy_status()
    elif cmd == "promote":
        if len(args) < 2: print("Usage: swiftdeploy promote canary|stable"); sys.exit(1)
        swiftdeploy_promote(args[1])
    # elif cmd == "audit": 
    #     swiftdeploy_audit()
    elif cmd == "teardown":
        swiftdeploy_teardown("--clean" in args)
    else:
        print(f"Unknown command: {cmd}"); sys.exit(1)

