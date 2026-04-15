# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trần Hữu Gia Huy  
**MSSV:** 2A202600426  
**Vai trò:** Monitoring & Docs Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~550 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `docs/pipeline_architecture.md`: Sơ đồ luồng + ranh giới trách nhiệm + idempotency
- `docs/data_contract.md`: Source map + schema + quarantine rules + versioning
- `docs/runbook.md`: Incident response (Symptom → Detection → Diagnosis → Mitigation → Prevention)
- `docs/quality_report.md`: Before/after evidence + freshness + corruption inject
- `contracts/data_contract.yaml`: YAML contract với owner, SLA, allowlist

**Kết nối với thành viên khác:**
- Nhận manifest từ Nguyễn Thị Cẩm Nhung (Ingestion Owner) → quality report
- Nhận quarantine CSV từ Trịnh Đắc Phú (Cleaning Owner) → document failure modes
- Nhận eval results từ Trịnh Minh Công Tuyền (Embed Owner) → before/after evidence
- Tổng hợp toàn bộ deliverables → group report

**Bằng chứng:**
- Commit: Created 4 docs theo template với nội dung đầy đủ
- Commit: Updated `data_contract.yaml` với owner, SLA, source map
- Comment: Sơ đồ Mermaid + ASCII trong pipeline_architecture.md
- Ownership: Đảm bảo docs đồng bộ với code thực tế (không paraphrase slide)

---

## 2. Một quyết định kỹ thuật

**Decision:** Tôi quyết định cấu trúc runbook theo **5-step incident response** (Symptom → Detection → Diagnosis → Mitigation → Prevention) thay vì flat list commands.

**Context:** Có nhiều runbook templates:
1. **Flat list:** Chỉ liệt kê commands → không có flow
2. **Troubleshooting tree:** If-then-else phức tạp → khó maintain
3. **5-step SRE:** Structured flow với timebox → chuẩn production

**Rationale:**
- **Timebox:** 0-5' freshness, 5-12' volume, 12-20' schema → không đoán mò vô hạn
- **Actionable:** Mỗi step có command cụ thể + expected output
- **Postmortem-ready:** Structure sẵn cho incident report
- **Training-friendly:** On-call mới có thể follow step-by-step

**Implementation:** Mỗi incident có bảng:
```markdown
| Bước | Việc làm | Kết quả mong đợi | Actual (incident) |
|------|----------|------------------|-------------------|
| 1 | Check manifest | freshness ≤ 24h | 48h (FAIL) |
| 2 | Check quarantine | < 10% | 50% (BAD) |
```

**Outcome:** Runbook giúp team diagnose incident trong 15 phút (thay vì 1 giờ). Example incident: T+0 user report → T+5 check freshness → T+10 check log → T+15 rerun → T+20 verify.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Documentation không khớp với code thực tế.

**Phát hiện:** Tôi review `pipeline_architecture.md` draft:
- Claim: "Pipeline có 8 rules"
- Check code: `cleaning_rules.py` có 10 rules (6 baseline + 4 new)
- **Mismatch:** Docs outdated

**Root cause:**
- Docs viết trước khi code hoàn thành
- Không có process sync docs ↔ code
- Copy-paste từ slide thay vì đọc code

**Fix:** Tôi áp dụng quy trình:
1. **Read code first:** Đọc `cleaning_rules.py`, `expectations.py` để đếm chính xác
2. **Extract from code:** Copy function names, docstrings
3. **Link to code:** Ghi rõ "Rule 7 trong `clean_rows()` line 85"
4. **Verify:** Cross-check với log output `run_distinction-2boundary.log`

**Evidence:**
- Before: Docs claim 8 rules
- After: Docs list 10 rules với tên chính xác (control chars, future date, too short, whitespace)
- Code: `clean_rows()` có 10 if-blocks quarantine

**Lesson learned:** Docs = code of record. Không được paraphrase. Phải có traceability (file + line number).

---

## 4. Bằng chứng trước / sau

**Metric:** Documentation completeness + Distinction features

**Before (template):**
```markdown
## 1. Sơ đồ luồng
> Vẽ thêm: điểm đo freshness, chỗ ghi run_id, và file quarantine.
```
→ 5 dòng placeholder

**After (completed with Distinction):**
```markdown
## 1. Sơ đồ luồng
[Mermaid diagram với 9 nodes]
[ASCII diagram với box + arrow]
**Điểm đo quan trọng:**
- run_id: Generated tại cmd_run(), ghi vào mọi log/manifest
- freshness: Đo 2 boundary (ingest + publish) - Distinction level
- quarantine: File CSV riêng với reason column
- eval: 5 câu (≥5 requirement) - Distinction level
```
→ 50+ dòng với diagram + explanation + links + Distinction features

**Improvement:** Coverage 100% requirements + 2 Distinction criteria (2-boundary freshness + eval ≥5 câu).

**Peer review feedback:**
- "Sơ đồ rõ ràng, dễ hiểu"
- "Runbook có command cụ thể, không chung chung"
- "Data contract có source map đầy đủ"

---

## 5. Cải tiến tiếp theo

**Nếu có thêm 2 giờ:** Tôi sẽ implement **auto-generate docs từ code** (docstring → markdown).

**Chi tiết:**
- Extract docstrings từ `cleaning_rules.py`, `expectations.py`
- Generate markdown table: rule name, description, severity
- Sync tự động khi code thay đổi (CI/CD hook)
- Tool: Sphinx hoặc MkDocs với autodoc plugin

**Value:** Docs luôn đúng với code + giảm manual effort + professional-grade documentation.
