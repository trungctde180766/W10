# ESO Setup

## 1. Tạo secret trong AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name prod/db/password \
  --secret-string "MyS3cr3tP@ss" \
  --region ap-southeast-1
```

## 2. Tạo AWS credentials Secret (MANUAL — không commit vào Git)

```bash
kubectl create secret generic aws-credentials \
  --from-literal=access-key-id=YOUR_AWS_ACCESS_KEY_ID \
  --from-literal=secret-access-key=YOUR_AWS_SECRET_ACCESS_KEY \
  -n demo
```

## 3. Deploy qua GitOps

```bash
kubectl apply -f secret-store.yaml
kubectl apply -f external-secret.yaml

# Verify
kubectl get externalsecret -n demo
kubectl get secret db-secret -n demo
```

## 4. Test rotation (< 60s)

```bash
# Xem password hiện tại
kubectl get secret db-secret -n demo -o jsonpath='{.data.password}' | base64 -d

# Đổi trong AWS
aws secretsmanager update-secret \
  --secret-id prod/db/password \
  --secret-string "NewP@ss123" \
  --region ap-southeast-1

# Đợi < 60s rồi check lại
sleep 60
kubectl get secret db-secret -n demo -o jsonpath='{.data.password}' | base64 -d
# Kết quả: NewP@ss123 ✓
```

## Pass criteria
- ExternalSecret status: `SecretSynced` + `READY=True`
- Secret rotate < 60s không restart pod
