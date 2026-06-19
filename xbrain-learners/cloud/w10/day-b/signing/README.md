# Cosign Setup

## 1. Generate key pair (chạy local, 1 lần)

```bash
cosign generate-key-pair
# Tạo ra: cosign.key (private) + cosign.pub (public)
```

⚠️ KHÔNG commit `cosign.key` vào Git!
✅ `cosign.pub` có thể commit (dùng để verify).

## 2. Lưu vào GitHub Secrets

Vào: Settings → Secrets and variables → Actions → New repository secret

| Name | Value |
|------|-------|
| `COSIGN_PRIVATE_KEY` | nội dung file `cosign.key` |
| `COSIGN_PASSWORD` | password bạn nhập lúc generate |

## 3. Paste public key vào image-policy.yaml

```bash
cat cosign.pub
# Copy và paste vào spec.authorities[0].key.data trong image-policy.yaml
```

## 4. Deploy Policy Controller + ClusterImagePolicy

```bash
# Cài Policy Controller
kubectl apply -f https://github.com/sigstore/policy-controller/releases/download/v0.8.0/release.yaml

# Deploy policy
kubectl apply -f image-policy.yaml
```

## 5. Test

```bash
# Unsigned image → reject
kubectl run test --image=nginx:latest -n demo
# Error: admission webhook denied the request: image signature verification failed

# Signed image (từ CI) → pass
kubectl run app --image=ghcr.io/YOUR_REPO/myapp:SHA -n demo
# pod/app created ✓
```
