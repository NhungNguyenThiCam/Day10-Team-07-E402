# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trịnh Đắc Phú  
**MSSV:** 2A202600322  
**Vai trò:** Cleaning & Quality Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~590 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `transform/cleaning_rules.py`: Hàm `clean_rows()` - implement 10 cleaning rules (6 baseline + 4 mới)
- `quality/expectations.py`: Hàm `run_expectations()` - implement 9 expectations (6 baseline + 3 mới)
- `artifacts/quarantine/*.csv`: Quarantine records với reason column

**Kết nối với thành viên khác:**
- Nhận raw data từ Nguyễn Thị Cẩm Nhung (Ingestion Owner) → clean
- Truyền cleaned data cho Trịnh Minh Công Tuyền (Embed Owner) → embed vào Chroma
- Truyền expectation results cho Nguyễn Thị Cẩm Nhung → log + halt decision
- Cung cấp quarantine CSV cho Trần Hữu Gia Huy (Docs Owner) → quality report

**Bằng chứng:**
- Commit: Added 4 rules mới trong `cleaning_rules.py` (control chars, future date, too short, whitespace)
- Commit: Added 3 expectations mới trong `expectations.py` (no duplicate chunk_ids, allowlist, distribution)
- Comment: `# Rule 7: Detect control characters or BOM`, `# E7: No duplicate chunk_ids`
- Ownership: Đảm bảo quarantine_records tracking chính xác, metric_impact table trong group report

---

## 2. Một quyết định kỹ thuật

**Decision:** Tôi quyết định chiến lược **quarantine all** với reason column thay vì silent drop hoặc halt ngay.

**Context:** Khi gặp record lỗi (duplicate, unknown doc_id, invalid date), có 3 options:
1. **Silent drop:** Bỏ qua không log → mất audit trail
2. **Quarantine:** Ghi vào file riêng với reason → có thể review/fix
3. **Halt:** Dừng pipeline ngay → quá strict cho production

**Rationale:**
- **Audit trail:** Compliance yêu cầu biết "record nào bị loại, vì sao" → quarantine CSV với reason column
- **Recovery:** Data Engineer có thể review `artifacts/quarantine/*.csv` và fix upstream issue
- **Debugging:** Quarantine giúp phát hiện pattern lỗi (VD: 40% quarantine = upstream schema drift)
- **Flexibility:** Expectation layer vẫn có thể halt nếu critical (VD: refund window sai)

**Implementation:** Mỗi rule quarantine với reason rõ ràng:
```python
if doc_id not in ALLOWED_DOC_IDS:
    quarantine.append({**raw, "reason": "unknown_doc_id"})
    continue
```

**Outcome:** Run `distinction-2boundary` có `quarantine_records=4` với reasons: duplicate_chunk_text, stale_hr_policy, unknown_doc_id, missing_effective_date. Tất cả có thể trace back để fix.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Expectation `refund_no_stale_14d_window` FAIL khi chạy inject run.

**Phát hiện:** Tôi chạy pipeline với `--no-refund-fix` flag:
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```
Log output:
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed
```

**Root cause:** Rule 6 (refund fix 14→7) bị bypass bởi flag `apply_refund_window_fix=False`. Chunk stale "14 ngày làm việc" pass qua clean layer → vào expectation layer → expectation đúng vai trò: **last line of defense**.

**Fix:** Tôi rerun pipeline chuẩn (không flag):
```bash
python etl_pipeline.py run --run-id distinction-2boundary
```
Log:
```
cleaned_records=6
quarantine_records=4
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
```

**Lesson learned:** Defense in depth - Rule fix + Expectation validate = 2 layers. Expectation không thay thế rule, chỉ detect. Halt có kiểm soát: `--skip-validate` chỉ dùng demo, production phải halt.

---

## 4. Bằng chứng trước / sau

**Metric:** `quarantine_records` count và expectation status

**Before (run_id: inject-bad):**
```
cleaned_records=8
quarantine_records=2
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
```
→ Chunk stale "14 ngày" vẫn trong cleaned → expectation FAIL

**After (run_id: distinction-2boundary):**
```
cleaned_records=6
quarantine_records=4
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
```
→ Chunk stale đã bị quarantine → expectation PASS

**Quarantine CSV evidence:**
```csv
chunk_id,doc_id,chunk_text,reason
2,policy_refund_v4,"Duplicate text",duplicate_chunk_text
7,hr_leave_policy,"10 ngày phép",stale_hr_policy_effective_date
9,legacy_catalog_xyz,"...",unknown_doc_id
```

**Improvement:** Rules mới phát hiện được 2 failure modes thêm (control chars, future date) → tăng coverage từ 6 → 10 rules.

---

## 5. Cải tiến tiếp theo

**Nếu có thêm 2 giờ:** Tôi sẽ tích hợp **Great Expectations (GE)** cho schema validation.

**Chi tiết:**
- Define ExpectationSuite trong `quality/ge_suite.json`
- Validate schema: column names, types, constraints (VD: chunk_id unique, doc_id in allowlist)
- Auto-generate data docs với GE dashboard
- Integrate vào pipeline: `df.validate()` trước khi embed

**Value:** Distinction level + schema drift detection tự động + professional-grade validation framework thay vì custom expectations.
