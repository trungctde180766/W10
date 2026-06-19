#!/bin/bash
# Lab: Verify 3 roles hoạt động đúng

echo "=== Verify RBAC Roles ==="

# 1. developer không đọc được Secret
echo "[1] Developer không đọc Secret:"
kubectl auth can-i get secret -n demo --as=alice
# Expected: no

# 2. developer deploy được
echo "[2] Developer deploy được:"
kubectl auth can-i create deployment -n demo --as=alice
# Expected: yes

# 3. sre đọc Secret được
echo "[3] SRE đọc Secret:"
kubectl auth can-i get secret -n demo --as=bob
# Expected: yes

# 4. viewer chỉ xem, không sửa
echo "[4] Viewer không sửa Deployment:"
kubectl auth can-i update deployment -n demo --as=carol
# Expected: no

echo "[5] Viewer xem Pod được:"
kubectl auth can-i get pod -n demo --as=carol
# Expected: yes

echo "=== Done ==="
