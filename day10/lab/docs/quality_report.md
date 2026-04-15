# Quality Report — Lab Day 10 (nhóm)

**run_id:** 2026-04-15T10-30Z  
**Ngày:** 2026-04-15  
**Nhóm:** Data Quality Team

---

## 1. Tóm tắt số liệu

### Run chuẩn (2026-04-15T10-30Z)

| Chỉ số | Trước (raw) | Sau (cleaned) | Ghi chú |
|--------|-------------|---------------|---------|
| raw_records | 10 | - | From policy_export_dirty.csv |
| cleaned_records | - | 7 | Passed all quality gates |
| quarantine_records | - | 3 | See breakdown below |
| Expectation halt? | - | NO | All 9 expectations passed |
| Freshness SLA | - | FAIL | age_hours=144.5 (data từ 2026-04-10, cố ý để demo) |

### Quarantine breakdown

| Reason | Count | Example |
|--------|-------|---------|
| duplicate_chunk_text | 1 | Row 2 (trùng row 1) |
| stale_hr_policy_effective_date | 1 | Row 7 (HR 2025 với 10 ngày phép) |
| unknown_doc_id | 1 | Row 9 (legacy_catalog_xyz_zzz) |
| **TOTAL** | **3** | **30% quarantine rate** |

---

## 2. Before / after retrieval (bắt buộc)

### Setup

- **Before run:** `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`
- **After run:** `python etl_pipeline.py run --run-id 2026-04-15T10-30Z` (chuẩn)
- **Eval:** `python eval_retrieval.py --out artifacts/eval/before_after_eval.csv`

### Câu hỏi then chốt: refund window (`q_refund_window`)

**Trước (inject-bad):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_id
q_refund_window,yes,yes,policy_refund_v4
```
- ❌ `hits_forbidden=yes`: Top-k chứa chunk "14 ngày làm việc" (stale)
- ⚠️ Agent có thể trả lời sai vì context lẫn cả v3 và v4

**Sau (2026-04-15T10-30Z):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_id
q_refund_window,yes,no,policy_refund_v4
```
- ✅ `hits_forbidden=no`: Không còn chunk stale trong top-k
- ✅ `contains_expected=yes`: Chunk chứa "7 ngày làm việc"
- ✅ Agent trả lời đúng policy v4

**Improvement:** `hits_forbidden` từ `yes` → `no` (100% improvement)

---

### Merit evidence: versioning HR — `q_leave_version`

**Trước (inject-bad):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_expected,top1_doc_id
q_leave_version,yes,yes,no,hr_leave_policy
```
- ❌ `hits_forbidden=yes`: Top-k chứa chunk "10 ngày phép năm" (HR 2025)
- ❌ `top1_doc_expected=no`: Top-1 đúng doc nhưng có thể là version cũ

**Sau (2026-04-15T10-30Z):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_expected,top1_doc_id
q_leave_version,yes,no,yes,hr_leave_policy
```
- ✅ `hits_forbidden=no`: Không còn chunk HR 2025 trong top-k
- ✅ `contains_expected=yes`: Chunk chứa "12 ngày phép năm"
- ✅ `top1_doc_expected=yes`: Top-1 đúng doc_id `hr_leave_policy`

**Improvement:** Version conflict resolved, `hits_forbidden` từ `yes` → `no`

---

## 3. Freshness & monitor

**Command:**
```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_2026-04-15T10-30Z.json
```

**Output:**
```
FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 144.5, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

**Interpretation:**
- **Status:** FAIL (cố ý để demo - data mẫu có `exported_at` cũ)
- **Age:** 144.5 giờ (6 ngày) > SLA 24 giờ
- **SLA choice:** 24h tại publish boundary (sau embed)
- **Production:** Nên đổi SLA thành 4h cho ticket stream, 24h cho policy PDF

**Rationale:**
- Policy PDF: thay đổi ít (1 lần/tháng) → SLA 24h OK
- Ticket stream: real-time → SLA 4h hoặc 1h
- Data mẫu: snapshot cũ để test freshness detection

---

## 4. Corruption inject (Sprint 3)

### Kịch bản inject

**Method 1: Flag `--no-refund-fix`**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```
- Không fix chunk "14 ngày làm việc" → "7 ngày làm việc"
- Expectation `refund_no_stale_14d_window` FAIL
- Bỏ qua halt với `--skip-validate` → embed dữ liệu xấu

**Method 2: Thêm dòng corrupt vào CSV**
- Thêm row với `chunk_text=""` (empty)
- Thêm row với `doc_id="malicious_doc"` (unknown)
- Thêm row với `effective_date="invalid"` (parse fail)

### Phát hiện

**Log evidence:**
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
```

**Eval evidence:**
```csv
q_refund_window,yes,yes,policy_refund_v4  # hits_forbidden=yes → BAD
```

**Quarantine evidence:**
```csv
chunk_id,doc_id,reason
5,policy_refund_v4,missing_chunk_text
9,legacy_catalog_xyz_zzz,unknown_doc_id
```

### Recovery

```bash
# Rerun pipeline chuẩn
python etl_pipeline.py run --run-id 2026-04-15T10-30Z

# Verify
python eval_retrieval.py --out artifacts/eval/after_fix.csv
# Check: hits_forbidden=no
```

---

## 5. Hạn chế & việc chưa làm

**Hạn chế hiện tại:**
- Freshness chỉ đo 1 boundary (publish), chưa đo ingest + clean riêng
- Alert channel chưa setup (TODO: Slack webhook)
- Không có staging → production promotion (embed trực tiếp)
- Concurrent run có thể race condition trên collection

**Việc chưa làm (nếu có thêm 2h):**
- [ ] Tích hợp Great Expectations (pydantic model validate)
- [ ] Freshness đo 2 boundary (ingest + publish)
- [ ] LLM-judge cho eval (thay vì keyword matching)
- [ ] Rule versioning đọc cutoff từ env (không hard-code 2026-01-01)
- [ ] Blue/green deployment cho vector index
- [ ] Automated rollback khi eval fail

**Distinction target:**
- Đã thêm 3 rule mới + 3 expectation mới (vượt yêu cầu ≥3 + ≥2)
- Có metric_impact cho mọi rule/expectation
- Có before/after evidence cho cả `q_refund_window` và `q_leave_version` (Merit)
- Cần thêm: freshness 2 boundary hoặc GE integration để đạt Distinction
