# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Data Quality Team  
**Thành viên:**
| Tên | MSSV | Vai trò (Day 10) | Email |
|-----|------|------------------|-------|
| Nguyễn Thị Cẩm Nhung (Nhóm trưởng) | 2A202600208 | Ingestion / Monitoring Owner | nguyencamnhung@example.com |
| Trịnh Đắc Phú | 2A202600322 | Cleaning & Quality Owner | trinhdacphu@example.com |
| Trịnh Minh Công Tuyền | 2A202600324 | Embed & Eval Owner | trinhcongtuyen@example.com |
| Trần Hữu Gia Huy | 2A202600426 | Documentation Owner | trangiahuy@example.com |

**Ngày nộp:** 2026-04-15  
**Repo:** https://github.com/team/day10-lab  
**Độ dài:** ~950 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** 18:00 (code/artifact); reports có thể muộn hơn nếu được phép  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval).

---

## 1. Pipeline tổng quan (180 từ)

**Nguồn raw:** CSV export mẫu `data/raw/policy_export_dirty.csv` (10 records) mô phỏng export từ PostgreSQL/API với các failure modes: duplicate, stale version, unknown doc_id, invalid date format, empty chunk.

**Luồng xử lý:**
```
Raw CSV (10 rows) 
  → Ingest (load_raw_csv) 
  → Clean (10 rules: allowlist, date parse, HR version, dedupe, refund fix, control chars, future date, too short, whitespace normalize) 
  → Validate (9 expectations: min rows, no empty doc_id, refund window, chunk length, ISO date, HR annual, unique chunk_id, allowlist compliance, distribution balance)
  → Embed (Chroma upsert by chunk_id + prune old vectors)
  → Monitor (freshness check SLA 24h)
```

**Kết quả:** 7 cleaned records, 3 quarantined (30% quarantine rate), 9/9 expectations passed, freshness FAIL (cố ý - data mẫu cũ 6 ngày).

**run_id lấy từ:** UTC timestamp tự động generate trong `cmd_run()` hoặc manual qua `--run-id` flag. Ghi vào log đầu tiên: `run_id=2026-04-15T10-30Z`.

**Lệnh chạy một dòng:**
```bash
cd lab && python etl_pipeline.py run && python eval_retrieval.py
```

---

## 2. Cleaning & expectation (220 từ)

**Baseline có sẵn:** 6 rules (allowlist doc_id, normalize date, stale HR < 2026-01-01, empty chunk, dedupe, refund 14→7) + 6 expectations (min rows, no empty doc_id, refund window, chunk length, ISO date, HR annual).

**Nhóm thêm:**
- **3 cleaning rules mới:** (1) detect control chars/BOM, (2) reject exported_at in future, (3) reject chunk < 10 chars, (4) normalize whitespace
- **3 expectations mới:** (7) no duplicate chunk_ids, (8) all doc_ids in allowlist, (9) distribution balance (warn)

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| Rule 7: control_chars_or_bom | quarantine=3 | quarantine=4 (nếu inject BOM) | Inject test: thêm `\ufeff` vào chunk → quarantined |
| Rule 8: exported_at_in_future | quarantine=3 | quarantine=4 (nếu inject future date) | Inject test: `exported_at=2027-01-01` → quarantined |
| Rule 9: chunk_too_short | quarantine=3 | quarantine=4 (nếu inject "abc") | Inject test: `chunk_text="abc"` (< 10 chars) → quarantined |
| Rule 10: normalize_whitespace | cleaned text có nhiều space | cleaned text single space | Log: chunk "A  B  C" → "A B C" |
| E7: no_duplicate_chunk_ids | expectation pass | expectation FAIL nếu hash collision | Rerun 2 lần: chunk_id stable → pass |
| E8: all_doc_ids_in_allowlist | expectation pass | expectation FAIL nếu có unknown doc | Row 9 (legacy_catalog) → quarantined trước expectation |
| E9: doc_id_distribution_balanced | warn (max_ratio=0.43) | warn (max_ratio=0.80) nếu skew | Log: `skew_ratio=2.0` (policy_refund=3, others=1-2) |

**Rule chính (baseline + mở rộng):**
1. Allowlist doc_id (baseline)
2. Normalize effective_date ISO (baseline)
3. Stale HR < 2026-01-01 (baseline)
4. Empty chunk_text (baseline)
5. Dedupe chunk_text (baseline)
6. Fix refund 14→7 (baseline)
7. **Control chars/BOM (NEW)**
8. **Exported_at future (NEW)**
9. **Chunk too short (NEW)**
10. **Normalize whitespace (NEW)**

**Expectation halt:**
- E1, E2, E3, E5, E6, E7, E8 = **halt** (critical)
- E4, E9 = **warn** (non-critical)

**Ví dụ 1 lần expectation fail:**
```
# Inject run:
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate

# Log output:
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
```

**Xử lý:** Rerun pipeline chuẩn (không flag) → expectation pass → embed clean data.

---

## 3. Before / after ảnh hưởng retrieval (240 từ)

**Kịch bản inject (Sprint 3):**

**Method:** Chạy pipeline với `--no-refund-fix --skip-validate` để embed dữ liệu có chunk stale "14 ngày làm việc".

```bash
# Before: inject corruption
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/before_inject.csv

# After: fix và rerun
python etl_pipeline.py run --run-id 2026-04-15T10-30Z
python eval_retrieval.py --out artifacts/eval/after_fix.csv
```

**Kết quả định lượng:**

| Metric | Before (inject-bad) | After (fix) | Improvement |
|--------|---------------------|-------------|-------------|
| `q_refund_window` contains_expected | yes | yes | - |
| `q_refund_window` hits_forbidden | **yes** ❌ | **no** ✅ | 100% |
| `q_leave_version` contains_expected | yes | yes | - |
| `q_leave_version` hits_forbidden | **yes** ❌ | **no** ✅ | 100% |
| `q_leave_version` top1_doc_expected | no | **yes** ✅ | Fixed |

**Giải thích:**
- **Before:** Top-k retrieval chứa cả chunk stale (14 ngày, 10 ngày phép) → agent có thể trả lời sai
- **After:** Chunk stale đã bị quarantine → top-k chỉ có chunk đúng version → agent trả lời đúng

**Evidence files:**
- `artifacts/eval/before_inject.csv` (hits_forbidden=yes)
- `artifacts/eval/after_fix.csv` (hits_forbidden=no)
- `artifacts/logs/run_inject-bad.log` (expectation FAIL)
- `artifacts/logs/run_2026-04-15T10-30Z.log` (expectation OK)

**Merit achievement:** Có chứng cứ cho cả `q_refund_window` (Pass) và `q_leave_version` (Merit) với đầy đủ 3 metrics (contains_expected, hits_forbidden, top1_doc_matches).

---

## 4. Freshness & monitoring (100 từ)

**SLA chọn:** 24 giờ tại publish boundary (sau embed vào Chroma)

**Command:**
```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_2026-04-15T10-30Z.json
```

**Output:** `FAIL {"age_hours": 144.5, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`

**Ý nghĩa:**
- **PASS:** Data tươi (≤ 24h) → production OK
- **WARN:** Data hơi cũ (24-48h) → cảnh báo team
- **FAIL:** Data quá cũ (> 48h) → halt pipeline hoặc alert on-call

**Manifest mẫu:** Data có `exported_at=2026-04-10T08:00:00` (6 ngày trước) → FAIL là đúng. Production sẽ có data tươi hơn.

**Rationale:** Policy PDF thay đổi ít → SLA 24h OK. Ticket stream real-time → nên SLA 1-4h.

---

## 5. Liên hệ Day 09 (80 từ)

**Tích hợp:** Dữ liệu sau embed vào collection `day10_kb` có thể được Day 09 multi-agent query.

**Shared domain:** CS + IT Helpdesk (refund, SLA, FAQ, HR, access) - cùng 5 policy documents trong `data/docs/`.

**Khác biệt:**
- **Day 09:** Focus orchestration (agent routing, tool calling)
- **Day 10:** Focus data quality (clean, validate, monitor)

**Value add:** Pipeline Day 10 đảm bảo agent Day 09 không đọc phải version cũ/sai → tăng trust score.

**Future work:** Tích hợp pipeline Day 10 làm upstream cho Day 09 corpus refresh (scheduled daily).

---

## 6. Rủi ro còn lại & việc chưa làm

**Rủi ro:**
- Concurrent pipeline runs → race condition trên Chroma collection
- Disk space full → embed fail (chưa có check)
- Schema drift upstream → parser break (chưa có schema version check)

**Việc chưa làm (nếu có thêm 2h):**
- [ ] Freshness đo 2 boundary (ingest + publish) → Distinction
- [ ] Great Expectations integration → Distinction
- [ ] Blue/green deployment cho vector index
- [ ] Automated rollback khi eval fail > 20%
- [ ] Alert channel Slack webhook setup

**Peer review feedback (3 câu hỏi):**
1. **Rerun duplicate?** → Không, vì upsert by chunk_id + prune old vectors
2. **Freshness đo ở đâu?** → Publish boundary (sau embed), đọc từ manifest `latest_exported_at`
3. **Quarantine đi đâu?** → File CSV riêng `artifacts/quarantine/*.csv` với `reason` column, cần Data Engineer review trước khi merge
