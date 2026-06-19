#!/bin/bash
# Lab: Test 4 Gatekeeper constraints đang enforce

echo "=== Test Gatekeeper Constraints ==="

# 1. Deploy thiếu label → phải bị reject
echo "[1] Thiếu label app/owner → reject:"
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bad-deploy
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels:
      run: bad
  template:
    metadata:
      labels:
        run: bad
    spec:
      containers:
      - name: bad
        image: nginx:1.25
EOF
# Expected: Error - Missing required labels

# 2. Container dùng tag latest → phải bị reject
echo "[2] Image latest → reject:"
kubectl run bad-latest --image=nginx:latest -n demo
# Expected: Error - must not use 'latest' tag

# 3. Container không có resource limits → phải bị reject
echo "[3] Thiếu resource limits → reject:"
kubectl run no-limits --image=nginx:1.25 -n demo
# Expected: Error - must have memory/cpu limits

# 4. Container privileged → phải bị reject
echo "[4] Privileged container → reject:"
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: bad-privileged
  namespace: demo
spec:
  containers:
  - name: priv
    image: nginx:1.25
    securityContext:
      privileged: true
    resources:
      limits:
        cpu: "100m"
        memory: "128Mi"
EOF
# Expected: Error - must not run as privileged

echo "=== Tất cả constraint đang enforce ==="
