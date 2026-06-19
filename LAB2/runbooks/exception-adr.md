# ADR: Exception cho CVE vendor chưa có patch

## Trạng thái
`ACTIVE` — Review lại: 2024-12-31

## Bối cảnh

Trivy scan pipeline (LAB 2.2) được cấu hình fail khi phát hiện CVE HIGH/CRITICAL.  
Tuy nhiên, một số CVE do vendor chưa release patch — block mãi sẽ chặn deploy hợp lệ.

## Quyết định

Cho phép exception **có thời hạn** cho CVE cụ thể chưa có patch bằng cách:

1. Thêm CVE ID vào file `.trivyignore` tại root repo
2. Ghi ADR này với lý do, ngày hết hạn, và người phê duyệt
3. Review lại định kỳ (tối đa 90 ngày)

## Cách thêm exception

```bash
# .trivyignore
CVE-2023-XXXXX  # Flask dependency, vendor patch ETA: 2024-Q1, reviewed by: @username
```

**Sau đó** cập nhật bảng Exception bên dưới.

## Bảng Exception hiện tại

| CVE ID | Package | Severity | Lý do exception | Ngày hết hạn | Người phê duyệt |
|--------|---------|----------|-----------------|--------------|-----------------|
| _(chưa có)_ | | | | | |

## Hậu quả

- ✅ Pipeline không bị block bởi CVE chưa có patch
- ✅ Có audit trail rõ ràng (ai approve, hết hạn khi nào)
- ⚠️ Phải review định kỳ — nếu quá hạn mà chưa review, exception tự hết hiệu lực
- ⚠️ Không được dùng exception để bypass CVE có patch sẵn

## Tham khảo

- [NIST NVD](https://nvd.nist.gov/)
- Trivy docs: https://aquasecurity.github.io/trivy/latest/docs/configuration/filtering/
