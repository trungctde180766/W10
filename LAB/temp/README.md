# W10 — Progressive Delivery + Security GitOps Lab

> **Mục tiêu tổng quan:** Xây dựng một hệ thống deploy ứng dụng trên Kubernetes theo chuẩn GitOps — mọi thay đổi đều đi qua Git, không ai được `kubectl apply` tay vào production. Kết hợp với phân quyền RBAC, kiểm soát policy bằng OPA Gatekeeper, canary deployment tự động, và alerting khi SLO bị vi phạm.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Luồng hoạt động chính](#3-luồng-hoạt-động-chính)
4. [App-of-Apps Pattern & Sync Wave](#4-app-of-apps-pattern--sync-wave)
5. [Lab 1.1 — RBAC: Phân quyền 3 vai trò](#5-lab-11--rbac-phân-quyền-3-vai-trò)
6. [Lab 1.2 — Gatekeeper: 4 luật chặn manifest xấu](#6-lab-12--gatekeeper-4-luật-chặn-manifest-xấu)
7. [Lab 1.3 — Custom Policy: Whitelist Registry](#7-lab-13--custom-policy-whitelist-registry)
8. [Flask API — Ứng dụng demo](#8-flask-api--ứng-dụng-demo)
9. [CI/CD Pipeline](#9-cicd-pipeline)
10. [Canary Deployment & AnalysisTemplate](#10-canary-deployment--analysistemplate)
11. [Monitoring, SLO & Alerting](#11-monitoring-slo--alerting)
12. [Hướng dẫn chạy từ đầu](#12-hướng-dẫn-chạy-từ-đầu)
13. [Kiểm tra kết quả](#13-kiểm-tra-kết-quả)

---

## 1. Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Developer máy local                        │
│  sửa code / YAML  →  git push  →  GitHub repo                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │         GitHub Actions CI        │
              │  - validate.yml: kubeconform     │
              │  - build-push.yml: build image   │
              │    → push ghcr.io, bump version  │
              └────────────────┬────────────────┘
                               │ git commit rollout.yaml (new version)
              ┌────────────────▼────────────────┐
              │            ArgoCD               │
              │  Detect thay đổi trong Git       │
              │  → sync App-of-Apps             │
              │  → deploy theo sync-wave order   │
              └────────────────┬────────────────┘
                               │
        ┌──────────────────────▼──────────────────────┐
        │              Kubernetes Cluster              │
        │                                             │
        │  ┌──────────────┐  ┌──────────────────────┐ │
        │  │  gatekeeper  │  │        RBAC          │ │
        │  │  Admission   │  │  alice/bob/carol     │ │
        │  │  Webhook     │  │  roles + bindings    │ │
        │  └──────┬───────┘  └──────────────────────┘ │
        │         │ chặn manifest vi phạm             │
        │  ┌──────▼───────────────────────────────┐   │
        │  │           namespace: demo            │   │
        │  │  Argo Rollout (canary 10→50→100%)    │   │
        │  │  Flask API pods (4 replicas)         │   │
        │  └──────────────┬───────────────────────┘   │
        │                 │ /metrics                   │
        │  ┌──────────────▼───────────────────────┐   │
        │  │        namespace: monitoring         │   │
        │  │  Prometheus → scrape metrics         │   │
        │  │  AnalysisRun → check success rate    │   │
        │  │  AlertManager → email khi SLO < 95% │   │
        │  └──────────────────────────────────────┘   │
        └─────────────────────────────────────────────┘
```

**Nguyên tắc cốt lõi:** Git là source of truth duy nhất. Kubernetes không được phép nhận lệnh trực tiếp từ tay người — mọi thứ phải đi qua commit → ArgoCD detect → sync.

---

## 2. Cấu trúc thư mục

```
temp/                              ← root của repo
│
├── src/api/                       ← Source code ứng dụng
│   ├── app.py                     ← Flask API (Python)
│   └── Dockerfile                 ← Build image python:3.13-alpine
│
├── app-api/                       ← Kubernetes manifests cho API
│   ├── rollout.yaml               ← Argo Rollout (canary strategy)
│   ├── service.yaml               ← Service expose port 80→8080
│   └── servicemonitor.yaml        ← ServiceMonitor (Prometheus scrape)
│
├── app-analysis/
│   └── analysis-template.yaml    ← AnalysisTemplate (tự chấm canary)
│
├── app-alert/
│   ├── prometheus-rules.yaml     ← PrometheusRule SLO alert
│   ├── email-secret.yaml.example ← Template secret Gmail (KHÔNG commit)
│   └── README.md                 ← Hướng dẫn setup email
│
├── app-common/
│   └── demo-namespace.yaml       ← Tạo namespace "demo"
│
├── rbac/                          ← Lab 1.1
│   ├── roles.yaml                 ← Role/developer + ClusterRole/sre + viewer
│   └── rolebindings.yaml          ← Bind alice/bob/carol vào roles
│
├── gatekeeper/constraints/        ← Lab 1.2 + 1.3
│   ├── no-latest-tag.yaml         ← Cấm image :latest
│   ├── require-resource-limits.yaml ← Bắt buộc cpu/memory limits
│   ├── no-run-as-root.yaml        ← Cấm runAsUser: 0
│   ├── no-host-network.yaml       ← Cấm hostNetwork: true
│   └── allowed-registry.yaml     ← Chỉ cho ghcr.io/Vuong-Bach/
│
├── argocd/
│   ├── root.yaml                  ← ROOT App (App-of-Apps entry point)
│   └── apps/                      ← Tất cả child Applications
│       ├── gatekeeper.yaml        ← Install Gatekeeper controller (wave -2)
│       ├── app-common.yaml        ← Namespace demo (wave -1)
│       ├── rbac.yaml              ← RBAC roles+bindings (wave -1)
│       ├── k8s-prometheus.yaml    ← Prometheus stack (wave 0)
│       ├── k8s-rollout.yaml       ← Argo Rollouts controller (wave 0)
│       ├── gatekeeper-constraints.yaml ← Constraints (wave 0)
│       ├── app-analysis.yaml      ← AnalysisTemplate (wave 1)
│       ├── app-alert.yaml         ← PrometheusRule (wave 1)
│       └── app-api.yaml           ← API Rollout (wave 2)
│
└── .github/workflows/
    ├── build-push.yml             ← CI: build + push Docker image
    └── validate.yml               ← CI: validate YAML manifest
```

---

## 3. Luồng hoạt động chính

Có 2 luồng quan trọng cần hiểu rõ:

### Luồng A — Deploy lần đầu (setup cluster)

```
1. Bạn chạy: kubectl apply -f argocd/root.yaml
                    │
                    ▼
2. ArgoCD root App được tạo
   → root.yaml trỏ vào folder argocd/apps/
   → ArgoCD đọc TẤT CẢ file .yaml trong đó
   → Tạo 9 child Applications
                    │
                    ▼
3. Các child Apps sync theo thứ tự sync-wave:
   Wave -2: gatekeeper controller cài lên (Helm)
   Wave -1: namespace "demo" tạo, RBAC apply
   Wave  0: Prometheus stack, Argo Rollouts, Gatekeeper Constraints
   Wave  1: AnalysisTemplate, PrometheusRule
   Wave  2: API Rollout + Service + ServiceMonitor
                    │
                    ▼
4. Cluster hoàn chỉnh, API đang chạy version 0.0.1
```

### Luồng B — Developer push code mới

```
1. Developer sửa src/api/app.py
   → git commit "feat: add new endpoint"
   → git push origin main
                    │
                    ▼
2. GitHub Actions kích hoạt build-push.yml:
   - Tính semantic version (feat → minor bump)
     ví dụ: 0.0.1 → 0.1.0
   - Build Docker image từ src/api/Dockerfile
   - Push lên ghcr.io/Vuong-Bach/w10-api:0.1.0
   - Tự động sed vào app-api/rollout.yaml:
       image: ghcr.io/Vuong-Bach/w10-api:0.1.0
   - Commit + push: "chore: bump version to v0.1.0"
   - Tạo git tag v0.1.0
                    │
                    ▼
3. ArgoCD detect rollout.yaml thay đổi
   → Sync app "api"
   → Gatekeeper Admission Webhook chặn nếu vi phạm policy
   → Nếu pass: Argo Rollouts bắt đầu canary
                    │
                    ▼
4. Canary deployment:
   Step 1: 10% traffic → version mới (90% → version cũ)
   Step 2: Pause 2 phút
           → AnalysisRun chạy, query Prometheus mỗi 30s
           → Kiểm tra success rate >= 90%
   Step 3: Nếu pass → 50% traffic
   Step 4: Pause 2 phút → kiểm tra lại
   Step 5: Nếu pass → 100% traffic (rollout hoàn tất)
           Nếu fail → AUTO ROLLBACK về version cũ
                    │
                    ▼
5. Prometheus theo dõi liên tục:
   - SLI: api:success_rate:5m (tỉ lệ request không lỗi 5xx)
   - Nếu success rate < 95% trong 2 phút → SLOViolation alert
   - AlertManager gửi email đến vuongbachdoan@gmail.com
```

---

## 4. App-of-Apps Pattern & Sync Wave

### App-of-Apps là gì?

Thay vì quản lý từng Application ArgoCD một cách riêng lẻ, pattern này dùng **1 Application "root" duy nhất** để quản lý tất cả các Application còn lại.

```
kubectl apply -f argocd/root.yaml   ← CHỈ CẦN CHẠY LỆNH NÀY 1 LẦN
       │
       ▼
ArgoCD Application "root"
  source: argocd/apps/             ← đọc toàn bộ folder này
       │
       ├── gatekeeper.yaml         → tạo Application "gatekeeper"
       ├── app-common.yaml         → tạo Application "common"
       ├── rbac.yaml               → tạo Application "rbac"
       ├── k8s-prometheus.yaml     → tạo Application "kube-prometheus-stack"
       ├── k8s-rollout.yaml        → tạo Application "argo-rollouts"
       ├── gatekeeper-constraints.yaml → tạo Application "gatekeeper-constraints"
       ├── app-analysis.yaml       → tạo Application "analysis"
       ├── app-alert.yaml          → tạo Application "alert"
       └── app-api.yaml            → tạo Application "api"
```

Lợi ích: Thêm component mới chỉ cần tạo 1 file YAML trong `argocd/apps/` → push Git → root App tự detect và deploy.

### Sync Wave — Tại sao cần thứ tự?

Một số tài nguyên phải có trước thì tài nguyên khác mới tạo được:
- Gatekeeper controller phải chạy TRƯỚC khi apply Constraints (vì Constraints dùng CRD của Gatekeeper)
- Namespace `demo` phải có TRƯỚC khi deploy RBAC và API vào đó
- Prometheus phải chạy TRƯỚC khi AnalysisTemplate query metrics

```
sync-wave: "-2"  →  gatekeeper (Helm chart, cài controller + CRD)
                        ↓ (đợi ready)
sync-wave: "-1"  →  common (tạo ns demo)
                 →  rbac (Role, ClusterRole, Bindings)
                        ↓
sync-wave: "0"   →  kube-prometheus-stack (Prometheus + AlertManager)
                 →  argo-rollouts (controller canary)
                 →  gatekeeper-constraints (4 rules + 1 custom policy)
                        ↓
sync-wave: "1"   →  analysis (AnalysisTemplate)
                 →  alert (PrometheusRule)
                        ↓
sync-wave: "2"   →  api (Rollout + Service + ServiceMonitor)
```

---

## 5. Lab 1.1 — RBAC: Phân quyền 3 vai trò

### Vấn đề cần giải quyết

Mặc định Kubernetes cluster không có phân quyền theo người dùng — ai cũng có thể làm mọi thứ nếu có kubeconfig. Lab này tạo 3 vai trò với quyền hạn khác nhau và bind vào 3 user cụ thể.

### 3 vai trò

| User | Vai trò | Loại | Scope | Được làm gì |
|------|---------|------|-------|-------------|
| `alice` | developer | `Role` | ns `demo` only | CRUD: deploy, pod, service, rollout |
| `bob` | sre | `ClusterRole` | toàn cụm | get/list/watch/exec/delete pods + nodes |
| `carol` | viewer | `ClusterRole` | toàn cụm | get/list/watch tất cả resources |

### Tại sao alice dùng Role còn bob/carol dùng ClusterRole?

- `Role` chỉ có hiệu lực trong **1 namespace** cụ thể. Alice chỉ được phép làm việc trong `demo`, không được đụng vào `kube-system` hay namespace khác.
- `ClusterRole` có hiệu lực **toàn cluster**. Bob cần xem pod ở mọi namespace để debug. Carol cần đọc mọi thứ để monitoring.

### Cách kiểm tra (sau khi deploy)

```bash
# alice có thể create deploy trong ns demo → yes
kubectl auth can-i create deploy -n demo --as alice

# alice KHÔNG thể create deploy trong kube-system → no
kubectl auth can-i create deploy -n kube-system --as alice

# bob có thể get pods toàn cụm (-A = all namespaces) → yes
kubectl auth can-i get pods -A --as bob

# carol KHÔNG thể delete nodes → no
kubectl auth can-i delete nodes --as carol
```

> `--as <user>` là impersonation — admin giả lập user để kiểm tra, không cần tạo user thật hay certificate.

### Files liên quan

- `rbac/roles.yaml` — định nghĩa 3 roles
- `rbac/rolebindings.yaml` — bind roles vào users
- `argocd/apps/rbac.yaml` — ArgoCD App deploy toàn bộ `rbac/`

---

## 6. Lab 1.2 — Gatekeeper: 4 luật chặn manifest xấu

### Vấn đề cần giải quyết

RBAC kiểm soát **ai** được làm gì. Nhưng RBAC không kiểm soát **nội dung** của manifest. Alice có quyền create deploy — nhưng Alice có thể deploy image `:latest`, không set resource limits, hay chạy root. OPA Gatekeeper chặn những thứ đó **tại admission** — ngay khi manifest được submit vào API server, trước khi được lưu vào etcd.

### Gatekeeper hoạt động như thế nào?

```
kubectl apply -f bad-deploy.yaml
         │
         ▼
  Kubernetes API Server
         │
         ▼
  Admission Webhook ──► Gatekeeper
         │                  │
         │              Đọc Constraints
         │              Chạy Rego rules
         │              ← vi phạm → REJECT với message
         │
  (nếu pass) → lưu vào etcd → tạo resource
```

Gatekeeper gồm 2 loại object:
- **ConstraintTemplate**: Định nghĩa loại rule + Rego logic (viết bằng ngôn ngữ policy Rego)
- **Constraint**: Instance của rule, chỉ định áp dụng cho resource nào, namespace nào

### 4 luật đã cài

**Luật 1 — Cấm image `:latest`** (`no-latest-tag.yaml`)

Image `:latest` là nguy hiểm vì không reproducible — cùng tag nhưng mỗi lần pull có thể là image khác nhau. Gây ra "it works on my machine" và không thể rollback chính xác.

```yaml
# Bị chặn:
image: nginx:latest
image: nginx          # không có tag cũng bị chặn

# Được phép:
image: nginx:1.27.0
image: ghcr.io/Vuong-Bach/w10-api:0.1.0
```

**Luật 2 — Bắt buộc `resources.limits`** (`require-resource-limits.yaml`)

Nếu container không set limits, nó có thể dùng hết CPU/memory của node, làm crash các pod khác. Bắt buộc khai báo để Kubernetes scheduler phân bổ đúng.

```yaml
# Bị chặn:
containers:
- name: api
  image: myapp:1.0   # không có resources

# Được phép:
containers:
- name: api
  image: myapp:1.0
  resources:
    limits:
      cpu: 200m
      memory: 128Mi
```

**Luật 3 — Cấm `runAsUser: 0`** (`no-run-as-root.yaml`)

Process trong container chạy với UID 0 (root) có thể leo thang đặc quyền, gây rủi ro bảo mật nghiêm trọng nếu container bị compromise.

```yaml
# Bị chặn:
securityContext:
  runAsUser: 0

# Được phép: không set (mặc định non-root) hoặc
securityContext:
  runAsUser: 1000
  runAsNonRoot: true
```

**Luật 4 — Cấm `hostNetwork: true`** (`no-host-network.yaml`)

`hostNetwork: true` cho phép pod dùng network interface của node host — có thể nghe traffic của toàn node, cực kỳ nguy hiểm.

```yaml
# Bị chặn:
spec:
  hostNetwork: true

# Được phép: không khai báo hostNetwork (mặc định false)
```

### Files liên quan

- `gatekeeper/constraints/*.yaml` — 4 ConstraintTemplate + Constraint
- `argocd/apps/gatekeeper.yaml` — cài Gatekeeper controller qua Helm
- `argocd/apps/gatekeeper-constraints.yaml` — deploy constraints

---

## 7. Lab 1.3 — Custom Policy: Whitelist Registry

### Vấn đề cần giải quyết

Dù đã cấm `:latest`, developer vẫn có thể pull image từ bất kỳ registry nào — DockerHub, quay.io, hay registry lạ không được vá bảo mật. Lab này tự viết Rego policy để chỉ cho phép image từ registry của team.

### Rego logic

```rego
# Chỉ cho phép image bắt đầu bằng prefix trong allowedPrefixes
violation[{"msg": msg}] {
  container := input_containers[_]
  not allowed_registry(container.image)
  msg := sprintf("Container '%v' dùng image '%v' từ registry không được phép.", ...)
}

allowed_registry(image) {
  prefix := input.parameters.allowedPrefixes[_]
  startswith(image, prefix)
}
```

### Constraint hiện tại cho phép

```yaml
parameters:
  allowedPrefixes:
  - "ghcr.io/Vuong-Bach/"
  - "ghcr.io/vuong-bach/"    # lowercase fallback
```

```
# Được phép:
ghcr.io/Vuong-Bach/w10-api:0.1.0   ✅

# Bị chặn:
nginx:1.27.0                        ❌  (DockerHub)
docker.io/library/python:3.13       ❌  (DockerHub)
quay.io/prometheus/node-exporter    ❌  (Quay)
```

### Cách thêm registry mới

Sửa `gatekeeper/constraints/allowed-registry.yaml`, thêm prefix vào `parameters.allowedPrefixes`, commit + push — ArgoCD tự sync.

---

## 8. Flask API — Ứng dụng demo

### app.py

```python
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))  # 0 = không có lỗi
VERSION    = os.getenv("VERSION", "v1")

GET /        → trả {"ok": true, "version": "v0.0.1"}
             → nếu random() < ERROR_RATE → trả 500 (lỗi giả inject)
GET /healthz → trả "ok" (dùng cho liveness/readiness probe)
GET /metrics → tự động expose bởi prometheus-flask-exporter
```

`ERROR_RATE` là công cụ test: set `0.15` = 15% request trả 500 → canary analysis sẽ fail → auto rollback.

### Dockerfile

```dockerfile
FROM python:3.13-alpine          # image nhỏ gọn
RUN pip install flask prometheus-flask-exporter
COPY app.py /app/app.py
WORKDIR /app
EXPOSE 8080
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
```

### Rollout manifest (`app-api/rollout.yaml`)

```yaml
spec:
  replicas: 4
  containers:
  - name: api
    image: ghcr.io/Vuong-Bach/w10-api:0.0.1   # CI tự update field này
    env:
    - name: ERROR_RATE
      value: "0"                               # CI tự update field này
    resources:
      limits:
        cpu: 200m
        memory: 128Mi                          # pass Gatekeeper constraint
```

---

## 9. CI/CD Pipeline

### Workflow 1: `validate.yml` — chạy khi có Pull Request

Khi mở PR chạm vào `app-api/`, `rbac/`, `gatekeeper/`, hoặc `argocd/`:

```
PR mở
  → kubeconform validate tất cả YAML manifest
  → -ignore-missing-schemas: bỏ qua CRD chưa biết schema
    (Rollout, Application, ServiceMonitor, ConstraintTemplate...)
  → Nếu YAML sai schema: PR bị block
  → Nếu pass: PR được merge
```

### Workflow 2: `build-push.yml` — chạy khi push lên main

```
git push main (có thay đổi src/api/)
  │
  ▼
1. Checkout code
2. Tính semantic version từ commit message:
   - "feat: ..."      → minor bump (0.0.1 → 0.1.0)
   - "fix: ..."       → patch bump (0.0.1 → 0.0.2)
   - "BREAKING CHANGE" → major bump (0.0.1 → 1.0.0)
3. Login vào ghcr.io bằng GITHUB_TOKEN
4. Build image: docker build ./src/api
5. Push với 3 tags:
   - :latest
   - :0.1.0
   - :v0.1.0-sha-abc1234
6. Tự động sed vào app-api/rollout.yaml:
   image: ghcr.io/Vuong-Bach/w10-api:0.1.0
   value: "v0.1.0"
7. git commit "chore: bump version to v0.1.0"
8. git push (trigger ArgoCD detect)
9. git tag v0.1.0
```

> **Quan trọng:** CI tự update `rollout.yaml` và push lại Git. Đây chính là cầu nối giữa CI (build image) và CD (ArgoCD deploy). Không cần webhook hay trigger thủ công.

---

## 10. Canary Deployment & AnalysisTemplate

### Canary là gì?

Thay vì deploy thẳng 100% traffic sang version mới (rủi ro cao), canary chuyển dần dần:
- Giai đoạn 1: 10% user thấy version mới, 90% vẫn dùng version cũ
- Quan sát metrics trong 2 phút
- Nếu ổn → tăng lên 50% → quan sát → tăng lên 100%
- Nếu phát hiện vấn đề → ngay lập tức rollback về 100% version cũ

### Strategy trong rollout.yaml

```yaml
strategy:
  canary:
    analysis:
      templates:
      - templateName: success-rate   # dùng AnalysisTemplate này
      startingStep: 1                # bắt đầu chấm từ step 1
    steps:
    - setWeight: 10      # 10% traffic → canary
    - pause: {duration: 2m}          # chờ 2 phút + chạy analysis
    - setWeight: 50      # 50% traffic → canary
    - pause: {duration: 2m}          # chờ 2 phút + chạy analysis
    - setWeight: 100     # 100% → hoàn tất
```

### AnalysisTemplate (`app-analysis/analysis-template.yaml`)

```yaml
metrics:
- name: success-rate
  interval: 30s                      # query Prometheus mỗi 30 giây
  successCondition: result >= 0.90   # pass nếu success rate ≥ 90%
  failureLimit: 10                   # cho phép tối đa 10 lần fail liên tiếp
  provider:
    prometheus:
      address: http://kube-prometheus-stack-prometheus.monitoring.svc:9090
      query: |
        scalar(
          sum(rate(flask_http_request_duration_seconds_count{status!~"5.."}[2m]))
          /
          sum(rate(flask_http_request_duration_seconds_count[2m]))
        )
```

Query Prometheus: đếm request không có status 5xx chia cho tổng request trong 2 phút → ra tỉ lệ thành công.

### Kịch bản test

```bash
# Test 1: Deploy thành công (ERROR_RATE=0)
# → AnalysisRun pass → canary tiến 10→50→100% → Synced

# Test 2: Deploy thất bại (ERROR_RATE=0.15 = 15% lỗi)
# → success rate = 85% < 90%
# → AnalysisRun fail sau 10 lần liên tiếp
# → Argo Rollouts AUTO ROLLBACK về version cũ
# → Không cần ai can thiệp

# Test 3: SLO alert (ERROR_RATE=0.10 = 10% lỗi)
# → success rate = 90% ≥ 90% → canary PASS (không rollback)
# → nhưng 90% < 95% SLO → PrometheusRule fire SLOViolation
# → AlertManager gửi email sau 2 phút
```

---

## 11. Monitoring, SLO & Alerting

### Stack monitoring

```
Flask API pod
  → /metrics endpoint (prometheus-flask-exporter)
  → ServiceMonitor (app-api/servicemonitor.yaml)
  → Prometheus scrape mỗi 15 giây
  → Tính SLI: api:success_rate:5m
  → Nếu < 0.95 trong 2 phút → PrometheusRule fire alert
  → AlertManager route → email receiver
  → Gửi email HTML đến vuongbachdoan@gmail.com
```

### SLI vs SLO

- **SLI** (Service Level Indicator): metric đo được — ở đây là `success rate = (request thành công) / (tổng request)`
- **SLO** (Service Level Objective): ngưỡng cam kết — ở đây là **95%**. Nếu xuống dưới → vi phạm SLO → phải alert

### PrometheusRule (`app-alert/prometheus-rules.yaml`)

```yaml
# Recording rule: tính sẵn metric để dùng nhanh
- record: api:success_rate:5m
  expr: |
    sum(rate(flask_http_request_duration_seconds_count{status!~"5.."}[5m]))
    /
    sum(rate(flask_http_request_duration_seconds_count[5m]))

# Alert rule: fire khi vi phạm SLO
- alert: SLOViolation
  expr: api:success_rate:5m < 0.95
  for: 2m      # phải dưới ngưỡng liên tục 2 phút mới fire (tránh false positive)
  labels:
    severity: critical
```

### Email Alert Setup (thủ công 1 lần)

```bash
# 1. Lấy Gmail App Password tại:
#    https://myaccount.google.com/apppasswords

# 2. Copy file example
cp app-alert/email-secret.yaml.example app-alert/email-secret.yaml

# 3. Điền password vào
# (sửa: your-gmail-app-password-16-chars → password thật)

# 4. Apply thủ công (file này bị .argocdignore, không được commit)
kubectl apply -f app-alert/email-secret.yaml
```

> File `email-secret.yaml` bị liệt vào `.argocdignore` và `.gitignore` — không bao giờ được commit vào Git vì chứa credential.

---

## 12. Hướng dẫn chạy từ đầu

### Yêu cầu

- Docker Desktop
- minikube
- kubectl
- git

### Bước 1 — Khởi động cluster

```bash
minikube start -p w10 --driver=docker --cpus=4 --memory=8g
kubectl config use-context w10
```

### Bước 2 — Cài ArgoCD

```bash
kubectl create ns argocd
kubectl apply --server-side -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Chờ ArgoCD ready
kubectl -n argocd rollout status deploy/argocd-server
```

### Bước 3 — Truy cập ArgoCD UI

```bash
# Port forward (chạy background)
kubectl -n argocd port-forward svc/argocd-server 8080:443 &

# Lấy password admin
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

# Mở browser: https://localhost:8080
# Login: admin / <password vừa lấy>
```

### Bước 4 — Deploy tất cả bằng 1 lệnh

```bash
# Trước: đổi repoURL nếu bạn fork repo về tên khác
# Sửa: https://github.com/Vuong-Bach/temp.git → URL repo của bạn
# Trong: argocd/root.yaml và tất cả argocd/apps/*.yaml

kubectl apply -f argocd/root.yaml
```

ArgoCD sẽ tự deploy tất cả theo đúng thứ tự sync-wave. Mở UI để theo dõi.

### Bước 5 — Setup email alert (optional)

```bash
cp app-alert/email-secret.yaml.example app-alert/email-secret.yaml
# Sửa password trong file
kubectl apply -f app-alert/email-secret.yaml
```

### Bước 6 — Verify tất cả up

```bash
# Check namespace demo
kubectl get all -n demo

# Check monitoring
kubectl get pod -n monitoring

# Check gatekeeper
kubectl get pod -n gatekeeper-system

# Check rollout
kubectl get rollout api -n demo
```

---

## 13. Kiểm tra kết quả

### Kiểm tra RBAC

```bash
# Kỳ vọng: yes
kubectl auth can-i create deploy -n demo --as alice

# Kỳ vọng: no (alice chỉ được phép trong ns demo)
kubectl auth can-i create deploy -n kube-system --as alice

# Kỳ vọng: yes (bob xem pods toàn cụm)
kubectl auth can-i get pods -A --as bob

# Kỳ vọng: no (carol chỉ đọc, không xóa node)
kubectl auth can-i delete nodes --as carol
```

### Kiểm tra Gatekeeper chặn manifest xấu

```bash
# Test cấm :latest
kubectl run bad --image=nginx:latest -n demo
# → Error: Container 'bad' dùng tag :latest — bị cấm.

# Test cấm no limits
kubectl apply -n demo -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bad-deploy
spec:
  replicas: 1
  selector:
    matchLabels: {app: bad}
  template:
    metadata:
      labels: {app: bad}
    spec:
      containers:
      - name: app
        image: ghcr.io/Vuong-Bach/w10-api:0.0.1
        # không có resources.limits
EOF
# → Error: Container 'app' thiếu resources.limits

# Test cấm registry lạ
kubectl apply -n demo -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bad-registry
spec:
  replicas: 1
  selector:
    matchLabels: {app: bad}
  template:
    metadata:
      labels: {app: bad}
    spec:
      containers:
      - name: app
        image: nginx:1.27.0
        resources:
          limits: {cpu: 100m, memory: 64Mi}
EOF
# → Error: registry không được phép. Chỉ cho phép: ["ghcr.io/Vuong-Bach/", ...]
```

### Kiểm tra Canary Rollout

```bash
# Xem trạng thái rollout
kubectl get rollout api -n demo -w

# Xem AnalysisRun
kubectl get analysisrun -n demo

# Xem chi tiết 1 analysis run
kubectl describe analysisrun -n demo <tên-run>
```

### Trigger test fail (auto rollback)

```bash
# Sửa ERROR_RATE trong rollout.yaml thành 0.15
# Commit + push → xem canary tự rollback
git add app-api/rollout.yaml
git commit -m "test: error rate 15% (should rollback)"
git push origin main

# Watch rollback
kubectl get rollout api -n demo -w
# Status sẽ chuyển: Progressing → Degraded → (tự rollback) → Healthy
```

### Cleanup

```bash
kubectl delete -f argocd/root.yaml
kubectl delete ns argocd demo monitoring gatekeeper-system argo-rollouts
minikube stop -p w10
minikube delete -p w10
```

---

## Tóm tắt nhanh

| Thành phần | Mục đích | File chính |
|-----------|----------|-----------|
| ArgoCD root | Entry point App-of-Apps | `argocd/root.yaml` |
| RBAC | Phân quyền alice/bob/carol | `rbac/` |
| Gatekeeper | Chặn manifest xấu tại admission | `gatekeeper/constraints/` |
| Argo Rollouts | Canary 10→50→100% | `app-api/rollout.yaml` |
| AnalysisTemplate | Tự chấm canary qua Prometheus | `app-analysis/` |
| Prometheus Stack | Metrics + AlertManager + Grafana | `argocd/apps/k8s-prometheus.yaml` |
| PrometheusRule | Alert khi SLO < 95% | `app-alert/prometheus-rules.yaml` |
| CI build-push | Build image + update manifest | `.github/workflows/build-push.yml` |
| CI validate | Kiểm tra YAML trước khi merge | `.github/workflows/validate.yml` |
