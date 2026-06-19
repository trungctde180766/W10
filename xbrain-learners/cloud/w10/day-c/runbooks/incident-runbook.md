# Runbook: Incident Response — K8s Cluster

> Format theo Google SRE Workbook. Cập nhật sau mỗi incident.

## Thông tin

| Field | Value |
|-------|-------|
| Service | w10-demo cluster |
| Owner | Platform Team |
| Last updated | 2026-06-18 |

---

## IR Playbook 6 bước

### Bước 1: DETECT
- Alert từ CloudWatch / Prometheus / GuardDuty
- Check: `kubectl get events -n demo --sort-by='.lastTimestamp'`
- Check: `kubectl top pods -n demo`

### Bước 2: TRIAGE
- Xác định scope: 1 pod / 1 namespace / toàn cluster?
- Classify severity: SEV1 (production down) / SEV2 (degraded) / SEV3 (minor)
- Notify: DM mentor Kiệt / Vương ngay nếu SEV1

### Bước 3: CONTAIN
```bash
# Cô lập pod nghi ngờ bị compromise
kubectl label pod <pod-name> -n demo quarantine=true
kubectl delete pod <pod-name> -n demo

# Nếu cô lập cả namespace
kubectl patch namespace demo -p '{"spec":{"finalizers":[]}}'

# Scale down deployment nghi ngờ
kubectl scale deployment <name> -n demo --replicas=0
```

### Bước 4: ERADICATE
```bash
# Xóa image độc hại khỏi registry
# Kiểm tra RBAC — ai đã deploy image này?
kubectl get rolebinding,clusterrolebinding -n demo -o yaml | grep -i subjects

# Rotate credentials bị lộ
aws secretsmanager update-secret \
  --secret-id prod/db/password \
  --secret-string "$(openssl rand -base64 20)" \
  --region ap-southeast-1
```

### Bước 5: RECOVER
```bash
# Deploy lại từ known-good image (có signature)
kubectl set image deployment/myapp \
  myapp=ghcr.io/YOUR_REPO/myapp:KNOWN_GOOD_SHA -n demo

# Verify healthy
kubectl rollout status deployment/myapp -n demo
kubectl get pods -n demo
```

### Bước 6: POST-MORTEM
- Viết postmortem trong vòng 48h
- Timeline: detect → contain → resolve
- Root cause
- Action items (có deadline + owner)

---

## Quick commands

```bash
# Xem tất cả pod đang chạy
kubectl get pods -n demo -o wide

# Xem log pod lỗi
kubectl logs <pod-name> -n demo --previous

# Check ai có quyền gì
kubectl auth can-i --list --as=alice -n demo

# Check ExternalSecret status
kubectl get externalsecret -n demo
kubectl describe externalsecret db-creds -n demo
```
