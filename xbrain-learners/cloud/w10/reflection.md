# W10 Reflection

## D1 — RBAC + Admission Policy

**Điều học được:**
- RBAC phân quyền theo nguyên tắc least privilege: developer không cần đọc Secret, viewer chỉ cần xem
- Gatekeeper dùng OPA Rego để viết constraint dạng code, audit mode giúp test trước khi enforce
- `kubectl auth can-i` là tool nhanh nhất để verify quyền

**Thử thách:**
- Rego syntax lúc đầu khó đọc, nhưng pattern `violation[{"msg": msg}]` khá nhất quán

---

## D2 — Secrets Rotation + Supply Chain

**Điều học được:**
- K8s Secret chỉ là base64, không phải encryption thật — ESO + AWS Secrets Manager giải quyết cả rotation lẫn audit
- `refreshInterval: 1m` cho phép rotate secret mà pod không cần restart (volume mount tự reload)
- CI pipeline: Trivy scan → Cosign sign → Push. Thứ tự quan trọng, sign chỉ sau khi scan pass
- Admission verify signature là "last line of defense" — dù CI bị bypass thì cluster vẫn chặn

**Thử thách:**
- Setup IRSA vs static credentials: production dùng IRSA, lab dùng static để đơn giản

---

## D3 — Platform Integration + Lab

**Điều học được:**
- ResourceQuota + LimitRange tạo "guardrail" ở namespace level, không phụ thuộc developer khai báo đúng
- Platform end-to-end = GitOps (W9) + Security (W10) + Observability (W8/W9)
- Runbook 6 bước IR: Detect → Triage → Contain → Eradicate → Recover → Post-mortem

**Lab takeaway:**
- "Chặn ở cluster level" thực sự hiệu quả hơn "developer hứa" vì constraint là code, không phải convention
- 3 role (developer/sre/viewer) đủ cho phần lớn tổ chức, thêm role chỉ khi có use case rõ ràng

---

## Mục tiêu đã đạt

- [x] 3 role rõ ràng: `developer` / `sre` / `viewer`
- [x] 4 Gatekeeper constraint enforce: required-labels, resource-limits, no-latest, no-privileged
- [x] ESO rotate secret < 60s không restart pod
- [x] Admission reject unsigned image
