# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Thị Cẩm Nhung  
**MSSV:** 2A202600208  
**Vai trò:** Ingestion & Monitoring Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~580 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `etl_pipeline.py`: Hàm `cmd_run()`, `cmd_freshness()`, `main()` - orchestration toàn pipeline từ ingest → clean → validate → embed → monitor
- `monitoring/freshness_check.py`: Hàm `check_manifest_freshness()` - kiểm tra SLA freshness với 2 boundary (ingest + publish)
- `artifacts/manifests/*.json`: Generate manifest với run_id, timestamps (ingest_timestamp, publish_timestamp), metrics (raw_records, cleaned_records, quarantine_records)
- `artifacts/logs/*.log`: Logging infrastructure với run_id tracking

**Kết nối với thành viên khác:**
- Nhận cleaned CSV từ Trịnh Đắc Phú (Cleaning Owner) → embed
- Nhận expectation results từ Trịnh Đắc Phú → log + halt decision
- Truyền cleaned data cho Trịnh Minh Công Tuyền (Embed Owner) → Chroma upsert
- Cung cấp manifest cho Trần Hữu Gia Huy (Docs Owner) → quality report

**Bằng chứng:**
- Commit: Modified `etl_pipeline.py` lines 60, 90-91 (capture 2 timestamps)
- Commit: Modified `monitoring/freshness_check.py` lines 35-60 (2-boundary mode)
- Comment trong code: `# Capture ingest timestamp (boundary 1)`, `# Capture publish timestamp (boundary 2)`
- Ownership: Điều phối 4 thành viên, review toàn bộ deliverables, đảm bảo run_id consistency

---

## 2. Một quyết định kỹ thuật

**Decision:** Tôi quyết định implement freshness monitoring với **2 boundary** (ingest + publish) thay vì 1 boundary như baseline.

**Context:** Baseline chỉ đo freshness tại publish boundary (sau embed). Để đạt Distinction level theo SCORING.md điều kiện (b), tôi mở rộng thành 2 boundary:
1. **Ingest boundary:** Timestamp khi load raw CSV (`ingest_timestamp`)
2. **Publish boundary:** Timestamp khi embed xong vào Chroma (`publish_timestamp`)

**Rationale:**
- **Bottleneck detection:** Phân biệt được "ingest chậm" (upstream issue) vs "processing chậm" (pipeline issue) vs "embed chậm" (Chroma issue)
- **SLA granular:** Có thể set SLA riêng cho từng stage (VD: ingest < 1h, processing < 30min, publish < 2h)
- **Observability:** Đo được `processing_time_hours` = publish - ingest để monitor pipeline performance

**Implementation:** Tôi capture 2 timestamps trong `cmd_run()` và modify `check_manifest_freshness()` để detect 2-boundary mode, calculate 3 metrics (ingest_age, publish_age, processing_time).

**Outcome:** Distinction achieved + Bonus +1 điểm. Processing time = 0.009h (~32 giây) cho 10 raw records → 6 cleaned → embed.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Sau khi chạy inject run (`--no-refund-fix --skip-validate`), eval cho câu `q_refund_window` trả về `hits_forbidden=yes` - nghĩa là top-k retrieval chứa chunk stale "14 ngày làm việc".

**Phát hiện:**
- Tôi chạy `python eval_retrieval.py --out artifacts/eval/before_inject.csv`
- Output CSV: `q_refund_window,yes,yes,policy_refund_v4`
- Metric `hits_forbidden=yes` → agent có thể trả lời sai vì context lẫn cả policy v3 (14 ngày) và v4 (7 ngày)

**Root cause:** Tôi check log `artifacts/logs/run_inject-bad.log`:
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed
```
→ Flag `--skip-validate` bypass halt, embed dữ liệu xấu vào Chroma.

**Fix:** Tôi rerun pipeline chuẩn (không flag):
```bash
python etl_pipeline.py run --run-id distinction-2boundary
python eval_retrieval.py --out artifacts/eval/distinction_5q_eval.csv
```

**Kết quả:** `hits_forbidden=no` (5/5 câu PASS). Manifest `distinction-2boundary.json` có `cleaned_records=6, quarantine_records=4` - chunk stale đã bị quarantine đúng.

---

## 4. Bằng chứng trước / sau

**Metric:** `hits_forbidden` cho câu `q_refund_window`

**Before (run_id: inject-bad):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_id
q_refund_window,yes,yes,policy_refund_v4
```
→ `hits_forbidden=yes`: Top-k chứa chunk "14 ngày làm việc" (stale)

**After (run_id: distinction-2boundary):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_id
q_refund_window,yes,no,policy_refund_v4
```
→ `hits_forbidden=no`: Không còn chunk stale trong top-k

**Log evidence (run_id: distinction-2boundary):**
```
cleaned_records=6
quarantine_records=4
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
embed_upsert count=6 collection=day10_kb
freshness_check=PASS {"mode": "2-boundary", "processing_time_hours": 0.009}
```

**Improvement:** `hits_forbidden` từ yes → no (100% fix). Grading: 3/3 PASS (gq_d10_01, gq_d10_02, gq_d10_03 đều đạt).

---

## 5. Cải tiến tiếp theo

**Nếu có thêm 2 giờ:** Tôi sẽ implement **alerting channel** cho freshness monitoring.

**Chi tiết:**
- Tích hợp Slack webhook: khi `freshness_check=FAIL` → post message tới channel #data-alerts
- Alert payload: run_id, age_hours, sla_hours, manifest_path
- Severity levels: WARN (24-48h) → yellow, FAIL (>48h) → red
- On-call rotation: tag @data-engineer khi FAIL

**Value:** Phát hiện data staleness real-time thay vì đợi manual check. Production-ready monitoring.
