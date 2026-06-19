# LAB 2 — Security & Multi-tenancy

Repo này mở rộng từ LAB 1, thêm 3 bài:

| Lab | Chủ đề | Kỹ thuật |
|-----|--------|----------|
| 2.1 | Rotate secret không restart pod | External Secrets Operator (ESO) + AWS Secrets Manager |
| 2.2 | Scan + ký + verify image | Trivy + Cosign + Sigstore Policy Controller |
| 2.3 | Đón team `payments` vào platform | Namespace isolation, RBAC, ResourceQuota, NetworkPolicy |

---

## Cấu trúc repo

```
eso/
├── secret-store.yaml        # SecretStore → AWS region + auth
└── external-secret.yaml     # map key AWS→K8s + refreshInterval

signing/
└── cosign.pub               # Public key (KHÔNG commit private key)

.github/workflows/
└── build-push.yml           # Trivy scan + Cosign sign trong CI

argocd/apps/
├── eso.yaml                 # App cài ESO operator (wave sớm)
├── eso-config.yaml          # App sync eso/ (wave SAU operator)
├── policy-controller.yaml   # App cài Sigstore Policy Controller
└── policies.yaml            # App sync policies/ (ClusterImagePolicy)

policies/
└── cluster-image-policy.yaml  # Chỉ cho phép image đã ký

app-payments/
├── namespace.yaml           # Namespace payments
├── rbac.yaml                # Role + RoleBinding least-privilege
├── resourcequota.yaml       # ResourceQuota + LimitRange
└── networkpolicy.yaml       # NetworkPolicy: default-deny + egress chặn demo

runbooks/
├── rotate-secret.md         # Runbook: cách rotate secret trên AWS
└── exception-adr.md         # ADR: exception cho CVE vendor chưa fix

argocd/apps/
└── app-payments.yaml        # ArgoCD App cho namespace payments
```

---

## Tự kiểm trước khi nộp

- [ ] ESO rotate < 60s, pod không restart (`kubectl get pod` → AGE không đổi)
- [ ] CI đỏ khi có CVE HIGH; unsigned image bị admission reject
- [ ] `git log -p | grep -i password` → không lộ secret
- [ ] Fresh cluster apply root → tự xanh

---

## Câu hỏi điểm cộng (README giải thích)

### 1. Vì sao guardrail cũ tự áp cho team B mà không cần viết luật mới?

Các Gatekeeper Constraint từ LAB 1 được tạo với `match.namespaces` rộng hoặc không giới hạn namespace cụ thể. Khi namespace `payments` được tạo và pod được deploy vào đó, admission webhook của Gatekeeper tự động evaluate mọi constraint có `match.kinds` phù hợp — **không cần tạo constraint mới**. Đây là lợi thế của policy-as-admission: viết một lần, áp toàn cluster.

### 2. Role/RoleBinding khác ClusterRoleBinding ra sao để giữ cô lập?

| | Role + RoleBinding | ClusterRoleBinding |
|---|---|---|
| Phạm vi | Chỉ trong 1 namespace | Toàn cluster |
| Cô lập tenant | ✅ User A chỉ thao tác ns của mình | ❌ Có thể đọc/ghi ns khác |
| Best practice | Multi-tenant | Admin/SRE toàn cụm |

`payments-dev` chỉ có Role trong ns `payments` → `kubectl auth can-i create deploy -n demo` sẽ trả về `no`.
