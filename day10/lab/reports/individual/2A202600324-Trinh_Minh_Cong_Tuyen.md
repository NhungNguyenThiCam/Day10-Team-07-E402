# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trịnh Minh Công Tuyền  
**MSSV:** 2A202600324  
**Vai trò:** Embed & Eval Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~570 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `etl_pipeline.py`: Hàm `cmd_embed_internal()` - embed logic với idempotency
- `eval_retrieval.py`: Script đánh giá retrieval quality (5 câu eval)
- `grading_run.py`: Script chạy grading questions (3 câu: gq_d10_01, gq_d10_02, gq_d10_03)
- Chroma collection `day10_kb`: Vector store management

**Kết nối với thành viên khác:**
- Nhận cleaned CSV từ Trịnh Đắc Phú (Cleaning Owner) → embed
- Nhận run_id từ Nguyễn Thị Cẩm Nhung (Ingestion Owner) → metadata tracking
- Cung cấp eval results cho Trần Hữu Gia Huy (Docs Owner) → quality report
- Cung cấp grading JSONL cho team → scoring

**Bằng chứng:**
- Commit: Implement idempotency strategy (upsert + prune) trong `cmd_embed_internal()`
- Commit: Expand eval từ 4 → 5 câu trong `test_questions.json` (Distinction requirement c)
- Comment: `# Idempotent: upsert theo chunk_id`, `# Prune old vectors`
- Ownership: Đảm bảo collection size stable khi rerun, grading 3/3 PASS

---

## 2. Một quyết định kỹ thuật

**Decision:** Tôi quyết định chiến lược idempotency với **upsert + prune** thay vì delete-all-insert.

**Context:** Khi rerun pipeline, có 3 strategies:
1. **Delete all → insert:** Đơn giản nhưng có downtime (collection rỗng tạm thời)
2. **Upsert only:** Không xóa vector cũ → collection phình dần
3. **Upsert + prune:** Upsert mới + xóa id không còn trong cleaned

**Rationale:**
- **No downtime:** Upsert atomic, không có khoảng trống collection rỗng → agent vẫn query được
- **No bloat:** Prune đảm bảo collection size = cleaned size → không waste storage
- **Idempotent:** Rerun 2 lần với cùng cleaned → cùng kết quả (deterministic)
- **Production-safe:** Không risk làm mất data tạm thời

**Implementation:**
```python
# Step 1: Get current IDs
prev = col.get(include=[])
prev_ids = set(prev.get("ids") or [])

# Step 2: Upsert new/updated
col.upsert(ids=ids, documents=documents, metadatas=metadatas)

# Step 3: Prune stale
drop = sorted(prev_ids - set(ids))
if drop:
    col.delete(ids=drop)
    log(f"embed_prune_removed={len(drop)}")
```

**Outcome:** Rerun 2 lần → collection size stable (6 vectors). Log `embed_prune_removed=0` khi rerun với cùng data.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Eval `hits_forbidden=yes` sau inject run - top-k chứa chunk stale.

**Phát hiện:** Tôi chạy eval sau inject:
```bash
python eval_retrieval.py --out artifacts/eval/before_inject.csv
```
Output: `q_refund_window,yes,yes,policy_refund_v4`
→ `hits_forbidden=yes` nghĩa là top-k chứa chunk "14 ngày làm việc" (forbidden keyword)

**Root cause:** Inject run embed chunk stale vào collection. Rerun chuẩn không prune được vì:
- Inject run: 8 vectors (7 cleaned + 1 stale)
- Rerun chuẩn: 6 vectors mới, nhưng 2 vectors cũ (từ inject) vẫn còn
- Prune logic chỉ xóa id không trong cleaned **hiện tại**, nhưng chunk_id có thể thay đổi nếu seq thay đổi

**Fix:** Tôi rerun pipeline chuẩn:
```bash
python etl_pipeline.py run --run-id distinction-2boundary
python eval_retrieval.py --out artifacts/eval/distinction_5q_eval.csv
```
Log: `embed_upsert count=6` (không còn stale)
Output: `hits_forbidden=no` (5/5 câu PASS)

**Lesson learned:** Prune is critical. Không prune → vector cũ làm ô nhiễm retrieval. chunk_id must be stable (deterministic hash).

---

## 4. Bằng chứng trước / sau

**Metric:** `hits_forbidden` cho 2 câu (refund + HR)

**Before (run_id: inject-bad):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_expected
q_refund_window,yes,yes,
q_leave_version,yes,yes,no
```
→ Top-k chứa chunk stale (14 ngày, 10 ngày phép)

**After (run_id: distinction-2boundary):**
```csv
question_id,contains_expected,hits_forbidden,top1_doc_expected
q_refund_window,yes,no,
q_leave_version,yes,no,yes
q_password_reset,yes,no,yes
```
→ Không còn chunk stale, eval expanded 5 câu (Distinction)

**Grading JSONL:**
```jsonl
{"id":"gq_d10_01","contains_expected":true,"hits_forbidden":false}
{"id":"gq_d10_02","contains_expected":true}
{"id":"gq_d10_03","contains_expected":true,"hits_forbidden":false,"top1_doc_matches":true}
```
→ 3/3 PASS (Merit + Distinction achieved)

**Improvement:** `hits_forbidden` từ yes → no (100% fix). Eval coverage từ 4 → 5 câu (+25%).

---

## 5. Cải tiến tiếp theo

**Nếu có thêm 2 giờ:** Tôi sẽ implement **blue/green deployment** cho vector index.

**Chi tiết:**
- Embed vào `day10_kb_staging` collection
- Chạy full eval suite trên staging (5 câu + grading 3 câu)
- Nếu pass → swap alias `day10_kb` → staging
- Nếu fail → rollback (giữ production collection)
- Automated rollback khi eval fail > 20%

**Value:** Zero-downtime deployment + production safety. Agent luôn query collection ổn định.
