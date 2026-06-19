# Runbook: Rotate DB Password (ESO + AWS Secrets Manager)

## Mục tiêu
Đổi DB password trên AWS → K8s Secret tự cập nhật < 60s → pod **không restart**.

## Điều kiện tiên quyết
- ESO operator đã cài và `SecretStore` status = Ready
- `ExternalSecret` `db-password` đã sync thành công

## Các bước

### 1. Đổi giá trị trên AWS Secrets Manager

```bash
aws secretsmanager put-secret-value \
  --secret-id demo/db-password \
  --secret-string '{"password":"new-super-secret-value"}'
```

### 2. Đợi ESO sync (tối đa 55s theo refreshInterval)

```bash
# Xem trạng thái sync
kubectl get externalsecret db-password -n demo

# Xem log ESO nếu cần debug
kubectl logs -n external-secrets deploy/external-secrets -f
```

### 3. Kiểm tra K8s Secret đã cập nhật

```bash
# Giá trị mới sẽ xuất hiện sau khi sync
kubectl get secret db-password -n demo \
  -o jsonpath='{.data.password}' | base64 -d
```

### 4. Kiểm tra pod KHÔNG restart

```bash
# AGE phải giữ nguyên (không có RESTARTS tăng)
kubectl get pod -n demo
```

**Lý do pod không restart**: App đọc secret qua `env.valueFrom.secretKeyRef`.  
Kubernetes không tự restart pod khi Secret thay đổi — pod đọc giá trị mới qua môi trường chỉ sau khi **restart tự nhiên** (hoặc rolling update).  
Nếu cần giá trị mới ngay lập tức mà không restart, dùng **volume mount** với `subPath` sẽ tự động cập nhật.

## Rollback

```bash
# Restore giá trị cũ trên AWS
aws secretsmanager put-secret-value \
  --secret-id demo/db-password \
  --secret-string '{"password":"old-value"}'
# ESO sẽ sync lại trong vòng 55s
```

## Kiểm chứng (nghiệm thu)

| Kiểm tra | Kỳ vọng |
|----------|---------|
| `kubectl get secret -o jsonpath` | Đổi theo < refreshInterval |
| `kubectl get pod` sau khi rotate | AGE không đổi (no restart) |
| `grep -ri password` trong repo | Không có secret thật |
