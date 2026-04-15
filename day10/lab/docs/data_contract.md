# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| PostgreSQL `policy_chunks` table | Batch export CSV qua cron (daily 02:00) | Connection timeout, partial export, schema drift | `raw_records` count, `exported_at` freshness |
| CRM API `/tickets/export` | REST API pagination (cursor-based) | Rate limit 429, partial JSON, auth token expire | HTTP status, `quarantine_records` (invalid JSON) |
| PDF storage S3 `s3://policies/` | File watcher + parser | OCR error, encoding issue, version conflict | File hash change, `effective_date` parse fail |
| HR system SFTP | SFTP pull + CSV parse | Network failure, file format change, stale data | File timestamp, `hr_leave_policy` version check |

**Owner:** Nhóm trưởng (Ingestion Owner)  
**SLA:** Freshness ≤ 24h tại publish boundary  
**Alert channel:** Slack #data-quality (TODO: setup webhook)

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | Format: `{doc_id}_{seq}_{hash16}` - ổn định cho idempotency |
| doc_id | string | Có | Allowlist: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy` |
| chunk_text | string | Có | Min length: 10 chars (sau normalize whitespace) |
| effective_date | date | Có | ISO format YYYY-MM-DD, parsed từ raw (hỗ trợ DD/MM/YYYY) |
| exported_at | datetime | Có | ISO 8601 với timezone, không được trong tương lai |

**Constraints:**
- `chunk_id` unique (checked by expectation E7)
- `doc_id` in allowlist (checked by expectation E8)
- `effective_date` >= 2026-01-01 for `hr_leave_policy` (rule 4)
- No control characters or BOM in `chunk_text` (rule 7)

---

## 3. Quy tắc quarantine vs drop

**Quarantine (ghi vào `artifacts/quarantine/*.csv` với `reason` column):**
- Unknown `doc_id` (không trong allowlist)
- Invalid date format (không parse được)
- Stale HR policy (effective_date < 2026-01-01)
- Empty chunk_text
- Duplicate chunk_text
- Control characters / BOM
- exported_at in future
- chunk_text too short (< 10 chars)

**Silent drop:** Không có - mọi record bị loại đều vào quarantine để audit

**Approval process:**
1. Data Engineer review `quarantine/*.csv`
2. Fix upstream source hoặc update allowlist/rules
3. Rerun pipeline với `--run-id` mới
4. Quarantine records không được embed vào production

**Owner:** Thành viên 2 (Cleaning & Quality Owner)

---

## 4. Phiên bản & canonical

**Source of truth:**

| Document | Canonical path | Version | Effective date | Owner |
|----------|---------------|---------|----------------|-------|
| Refund policy | `data/docs/policy_refund_v4.txt` | v4 | 2026-02-01 | Product team |
| SLA P1 | `data/docs/sla_p1_2026.txt` | 2026 | 2026-02-01 | Support team |
| IT FAQ | `data/docs/it_helpdesk_faq.txt` | living doc | 2026-02-01 | IT team |
| HR leave | `data/docs/hr_leave_policy.txt` | 2026 | 2026-02-01 | HR team |

**Version control:**
- **Refund policy**: v4 = 7 ngày, v3 = 14 ngày (stale - phải fix)
- **HR leave**: 2026 = 12 ngày phép, 2025 = 10 ngày phép (conflict - phải quarantine)

**Cutoff date:** `hr_leave_min_effective_date: 2026-01-01` (trong `data_contract.yaml`)

**Change management:**
1. Update canonical file in `data/docs/`
2. Update `effective_date` in export
3. Rerun pipeline → old version auto-quarantined
4. Update `data_contract.yaml` version field

**Lineage:** Mỗi chunk có `run_id` trong metadata để trace back manifest
