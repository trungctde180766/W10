from flask import Flask, jsonify, render_template, request
import subprocess, json, threading, time, os

app = Flask(__name__)

# ── helper ──────────────────────────────────────────────────────────────────
def run(cmd: list[str], timeout=30) -> dict:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "out": r.stdout.strip(), "err": r.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "out": "", "err": "Timeout"}
    except Exception as e:
        return {"ok": False, "out": "", "err": str(e)}

def kubectl(*args):
    return run(["kubectl"] + list(args))

def git_run(*args):
    return run(["git"] + list(args), timeout=60)

# ── routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ---------- CLUSTER STATUS ---------------------------------------------------
@app.route("/api/status")
def status():
    apps    = kubectl("get","applications","-n","argocd","-o","json")
    pods    = kubectl("get","pods","--all-namespaces","-o","json")
    nodes   = kubectl("get","nodes","-o","json")
    rollout = kubectl("get","rollout","api","-n","demo","-o","json")
    return jsonify({
        "applications": _parse_apps(apps),
        "pods":         _parse_pods(pods),
        "nodes":        _parse_nodes(nodes),
        "rollout":      _parse_rollout(rollout),
    })

def _parse_apps(r):
    if not r["ok"]: return []
    try:
        items = json.loads(r["out"])["items"]
        return [{"name": i["metadata"]["name"],
                 "sync":   i["status"].get("sync",{}).get("status","Unknown"),
                 "health": i["status"].get("health",{}).get("status","Unknown")}
                for i in items]
    except: return []

def _parse_pods(r):
    if not r["ok"]: return []
    try:
        items = json.loads(r["out"])["items"]
        return [{"name":  p["metadata"]["name"],
                 "ns":    p["metadata"]["namespace"],
                 "status":p["status"].get("phase","Unknown"),
                 "ready": all(c.get("ready") for c in p["status"].get("containerStatuses",[]))}
                for p in items]
    except: return []

def _parse_nodes(r):
    if not r["ok"]: return []
    try:
        items = json.loads(r["out"])["items"]
        return [{"name": n["metadata"]["name"],
                 "status": next((c["type"] for c in n["status"]["conditions"] if c["status"]=="True"),"Unknown")}
                for n in items]
    except: return []

def _parse_rollout(r):
    if not r["ok"]: return None
    try:
        d = json.loads(r["out"])
        return {"status":   d["status"].get("phase","Unknown"),
                "desired":  d["spec"]["replicas"],
                "ready":    d["status"].get("readyReplicas",0),
                "canary":   d["status"].get("currentStepIndex",None)}
    except: return None

# ---------- RBAC CHECKS ------------------------------------------------------
@app.route("/api/rbac/check")
def rbac_check():
    tests = [
        ("alice", "create", "deploy", "demo",        True),
        ("alice", "create", "deploy", "kube-system",  False),
        ("bob",   "get",    "pods",   None,            True),
        ("carol", "delete", "nodes",  None,            False),
    ]
    results = []
    for user, verb, res, ns, expected in tests:
        cmd = ["auth","can-i", verb, res, "--as", user]
        if ns: cmd += ["-n", ns]
        r = kubectl(*cmd)
        actual = r["out"].strip().lower() == "yes"
        results.append({
            "user": user, "verb": verb, "resource": res,
            "namespace": ns or "cluster-wide",
            "expected": expected, "actual": actual,
            "pass": actual == expected,
            "raw": r["out"]
        })
    return jsonify(results)

# ---------- GATEKEEPER -------------------------------------------------------
@app.route("/api/gatekeeper/test", methods=["POST"])
def gatekeeper_test():
    test_type = request.json.get("type","latest")
    manifests = {
        "latest": {
            "desc": "Deploy với image :latest (phải bị chặn)",
            "yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: gk-test-latest
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels: {app: gk-test}
  template:
    metadata:
      labels: {app: gk-test}
    spec:
      containers:
      - name: app
        image: nginx:latest
        resources:
          limits: {cpu: 100m, memory: 64Mi}"""
        },
        "no-limits": {
            "desc": "Deploy không có resource limits (phải bị chặn)",
            "yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: gk-test-nolimits
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels: {app: gk-test}
  template:
    metadata:
      labels: {app: gk-test}
    spec:
      containers:
      - name: app
        image: ghcr.io/trungctde180766/w10-api:0.0.1"""
        },
        "bad-registry": {
            "desc": "Deploy từ DockerHub (phải bị chặn)",
            "yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: gk-test-registry
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels: {app: gk-test}
  template:
    metadata:
      labels: {app: gk-test}
    spec:
      containers:
      - name: app
        image: nginx:1.27.0
        resources:
          limits: {cpu: 100m, memory: 64Mi}"""
        },
        "host-network": {
            "desc": "Deploy với hostNetwork: true (phải bị chặn)",
            "yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: gk-test-hostnet
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels: {app: gk-test}
  template:
    metadata:
      labels: {app: gk-test}
    spec:
      hostNetwork: true
      containers:
      - name: app
        image: ghcr.io/trungctde180766/w10-api:0.0.1
        resources:
          limits: {cpu: 100m, memory: 64Mi}"""
        }
    }
    m = manifests.get(test_type, manifests["latest"])
    # write temp file
    tmp = f"C:/tmp/gk-test-{test_type}.yaml"
    os.makedirs("C:/tmp", exist_ok=True)
    with open(tmp,"w") as f: f.write(m["yaml"])
    r = run(["kubectl","apply","-f", tmp, "--dry-run=server"])
    # cleanup
    try: os.remove(tmp)
    except: pass
    blocked = not r["ok"]
    return jsonify({
        "desc":    m["desc"],
        "blocked": blocked,
        "pass":    blocked,
        "message": r["err"] if blocked else r["out"]
    })

# ---------- CANARY CONTROL ---------------------------------------------------
@app.route("/api/canary/status")
def canary_status():
    r = kubectl("get","rollout","api","-n","demo","-o","json")
    if not r["ok"]: return jsonify({"error": r["err"]})
    try:
        d   = json.loads(r["out"])
        st  = d["status"]
        return jsonify({
            "phase":        st.get("phase","Unknown"),
            "readyReplicas":st.get("readyReplicas",0),
            "desiredReplicas": d["spec"]["replicas"],
            "currentStep":  st.get("currentStepIndex"),
            "conditions":   [{"type":c["type"],"status":c["status"],"msg":c.get("message","")}
                             for c in st.get("conditions",[])],
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/canary/set-error-rate", methods=["POST"])
def set_error_rate():
    rate = float(request.json.get("rate", 0))
    if not 0 <= rate <= 1:
        return jsonify({"ok": False, "err": "rate phải từ 0 đến 1"})
    # Patch đầy đủ cả env lẫn resources để không bị Gatekeeper chặn
    patch = json.dumps({"spec":{"template":{"spec":{"containers":[{
        "name": "api",
        "env": [
            {"name": "ERROR_RATE", "value": str(rate)},
            {"name": "VERSION",    "value": "v0.0.1"}
        ],
        "resources": {
            "limits": {"cpu": "200m", "memory": "128Mi"}
        }
    }]}}}})
    r = kubectl("patch","rollout","api","-n","demo","--type=merge","-p", patch)
    return jsonify({"ok": r["ok"], "out": r["out"], "err": r["err"]})

@app.route("/api/canary/rollback", methods=["POST"])
def canary_rollback():
    r = kubectl("argo","rollouts","undo","api","-n","demo")
    if not r["ok"]:
        # fallback
        r = run(["kubectl","argo","rollouts","undo","api","-n","demo"])
    return jsonify({"ok": r["ok"], "out": r["out"], "err": r["err"]})

# ---------- ARGOCD SYNC ------------------------------------------------------
@app.route("/api/argocd/sync", methods=["POST"])
def argocd_sync():
    app_name = request.json.get("app","root")
    r = kubectl("annotate","application", app_name,"-n","argocd",
                "argocd.argoproj.io/refresh=hard","--overwrite")
    return jsonify({"ok": r["ok"], "out": r["out"], "err": r["err"]})

# ---------- GIT INFO ---------------------------------------------------------
@app.route("/api/git/log")
def git_log():
    r = git_run("log","--oneline","-10")
    lines = [l for l in r["out"].split("\n") if l] if r["ok"] else []
    return jsonify({"ok": r["ok"], "commits": lines})

# ---------- LOGS -------------------------------------------------------------
@app.route("/api/logs/<namespace>/<pod>")
def pod_logs(namespace, pod):
    r = kubectl("logs", pod, "-n", namespace, "--tail=50")
    return jsonify({"ok": r["ok"], "logs": r["out"], "err": r["err"]})

# ---------- PROMETHEUS METRICS ----------------------------------------------
PROM = "http://localhost:9091"

@app.route("/api/metrics/slo")
def metrics_slo():
    import urllib.request, urllib.parse
    results = {}
    queries = {
        "success_rate": 'api:success_rate:5m',
        "rps":          'sum(rate(flask_http_request_duration_seconds_count{namespace="demo"}[2m]))',
        "error_rate":   'sum(rate(flask_http_request_duration_seconds_count{namespace="demo",status=~"5.."}[2m])) / sum(rate(flask_http_request_duration_seconds_count{namespace="demo"}[2m]))',
        "p99":          'histogram_quantile(0.99, sum(rate(flask_http_request_duration_seconds_bucket{namespace="demo"}[2m])) by (le))',
    }
    for key, q in queries.items():
        try:
            url = f"{PROM}/api/v1/query?query={urllib.parse.quote(q)}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            res = data["data"]["result"]
            results[key] = float(res[0]["value"][1]) if res else None
        except Exception as e:
            results[key] = None
    return jsonify(results)

@app.route("/api/metrics/alerts")
def metrics_alerts():
    import urllib.request
    try:
        url = f"{PROM}/api/v1/alerts"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        alerts = data["data"]["alerts"]
        # Lọc bỏ alert noise của minikube (component không expose cho Prometheus)
        NOISE = {"Watchdog","KubeControllerManagerDown","KubeSchedulerDown",
                 "etcdMembersDown","etcdInsufficientMembers","TargetDown"}
        return jsonify([{
            "name":     a["labels"].get("alertname",""),
            "severity": a["labels"].get("severity",""),
            "state":    a["state"],
            "summary":  a["annotations"].get("summary",""),
            "desc":     a["annotations"].get("description",""),
        } for a in alerts
          if a["labels"].get("alertname") not in NOISE])
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/metrics/history")
def metrics_history():
    import urllib.request, urllib.parse, time as t
    end   = int(t.time())
    start = end - 600  # last 10 min
    q = 'api:success_rate:5m'
    try:
        url = f"{PROM}/api/v1/query_range?query={urllib.parse.quote(q)}&start={start}&end={end}&step=30"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        res = data["data"]["result"]
        if res:
            return jsonify({"values": [[v[0], float(v[1])] for v in res[0]["values"]]})
        return jsonify({"values": []})
    except Exception as e:
        return jsonify({"error": str(e), "values": []})

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
