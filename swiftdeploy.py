import sys, os, subprocess, time, json, socket, yaml, ruamel.yaml
from jinja2 import Environment, FileSystemLoader


MANIFEST= "manifest.yaml"

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
    print(image)
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


# swiftdeploy deploy
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
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=3)
            print("✓ Stack is healthy")
            return
        except:
            time.sleep(3)
    print("✗ Health check timed out after 60s"); sys.exit(1)


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
    subprocess.run(["docker", "compose", "restart", service])

    # confirm switching
    time.sleep(3)
    import urllib.request
    port = manifest["nginx"]["port_on_host"]
    response = urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=5).read()
    print(f"Mode switched to {target}. /healthz: {response.decode()}")

# tear down/bring down everything
def teardown(clean=False):
    subprocess.run(["docker", "compose", "down"], capture_output=True)
    if clean == True:
        for f in ["nginx.conf", "docker-compose.yaml"]:
            if os.path.exists(f):
                os.remove(f)
        print("Generated Files removed")





swiftdeploy_init()
swiftdeploy_validate()
swiftdeploy_deploy()
swiftdeploy_promote('canary')
teardown(clean=True)