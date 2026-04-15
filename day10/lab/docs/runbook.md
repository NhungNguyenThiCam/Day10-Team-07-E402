# Runbook — Lab Day 10 (incident tối giản)

**Last updated:** 2026-04-15  
**Owner:** Nhóm trưởng (Monitoring Owner)

---

## Symptom

**User report:** Agent trả lời "Khách hàng có 14 ngày để yêu cầu hoàn tiền" thay vì "7 ngày"

**Observable behavior:**
- Retrieval eval `hits_forbidden=yes` cho câu `q_refund_window`
- User phản đối policy không đúng
- Trust score giảm

---

## Detection

**Metric báo động:**

1. **Freshness check FAIL:**
   ```bash
   python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
   # Output: FAIL {"reason": "freshness_sla_exceeded", "age_hours": 48.5, "sla_hours": 24}
   ```

2. **Expectation fail:**
   ```
   expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
   ```

3. **Eval `hits_forbidden`:**
   ```csv
   question_id,contains_expected,hits_forbidden
   q_refund_window,yes,yes  # ← BAD: có chunk stale trong top-k
   ```

**Dashboard (nếu có):**
- Freshness SLA: RED (> 24h)
- Quarantine count: spike từ 2 → 5
- Expectation pass rate: 88% (giảm từ 100%)

---

## Diagnosis

**Timebox:** 0-5' freshness, 5-12' volume/errors, 12-20' schema/lineage

| Bước | Việc làm | Kết quả mong đợi | Actual (incident example) |
|------|----------|------------------|---------------------------|
| 1 | Kiểm tra `artifacts/manifests/manifest_<latest>.json` | `latest_exported_at` trong 24h | `latest_exported_at: 2026-04-08T08:00:00` (48h cũ) |
| 2 | Mở `artifacts/quarantine/quarantine_<latest>.csv` | Ít hơn 10% raw_records | 5/10 records (50% - BAD) |
| 3 | Chạy `python eval_retrieval.py` | `hits_forbidden=no` cho tất cả | `q_refund_window: hits_forbidden=yes` |
| 4 | Đọc log `artifacts/logs/run_<latest>.log` | Tất cả expectation OK | `expectation[refund_no_stale_14d_window] FAIL` |
| 5 | Check Chroma collection count | Khớp `cleaned_records` | 7 vectors (khớp) nhưng có vector cũ |

**Root cause identified:**
- Pipeline chạy với flag `--no-refund-fix` (hoặc rule bị comment)
- Chunk "14 ngày làm việc" không được fix → pass qua clean
- Expectation detect nhưng bị `--skip-validate` → embed vào production
- Vector cũ không bị prune → còn trong top-k retrieval

**Evidence:**
```bash
# Log shows:
no_refund_fix=true
skipped_validate=true
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed
```

---

## Mitigation

**Immediate (< 5 phút):**

1. **Rollback embed** (nếu có backup):
   ```bash
   # Restore previous good collection (nếu có snapshot)
   # Hoặc: rerun pipeline chuẩn
   python etl_pipeline.py run --run-id hotfix-$(date +%s)
   ```

2. **Banner warning** (nếu không rollback được ngay):
   ```
   Agent UI: "⚠️ Dữ liệu đang cập nhật, vui lòng kiểm tra lại policy trên trang chính thức"
   ```

3. **Verify fix:**
   ```bash
   python eval_retrieval.py --out artifacts/eval/after_hotfix.csv
   # Check: hits_forbidden=no
   ```

**Timeline:**
- T+0: Detect (freshness alert)
- T+5: Diagnose (check manifest + log)
- T+10: Mitigate (rerun pipeline)
- T+15: Verify (eval pass)
- T+20: Remove banner

---

## Prevention

**Short-term (Sprint 4):**

1. **Thêm expectation halt mạnh hơn:**
   ```python
   # Đã có: E3 check refund_no_stale_14d_window (halt)
   # Thêm: E10 check không có --skip-validate trong production
   ```

2. **Alert channel:**
   ```yaml
   # data_contract.yaml
   freshness:
     alert_channel: "slack://hooks.slack.com/services/XXX"
     on_fail: page_oncall
   ```

3. **Pre-commit hook:**
   ```bash
   # .git/hooks/pre-commit
   if grep -q "skip-validate" etl_pipeline.py; then
     echo "ERROR: --skip-validate chỉ dùng cho demo"
     exit 1
   fi
   ```

**Long-term (Day 11 - Guardrails):**

1. **Staging → Production promotion:**
   - Embed vào `day10_kb_staging` trước
   - Chạy full eval suite
   - Swap alias `day10_kb` → staging nếu pass

2. **Automated rollback:**
   - Giữ 3 manifest gần nhất
   - Auto-rollback nếu eval fail > 20%

3. **Owner accountability:**
   - Mỗi run_id có owner trong manifest
   - Incident postmortem gắn owner

**Action items:**
- [ ] Setup Slack webhook (Owner: Nhóm trưởng)
- [ ] Thêm expectation E10 (Owner: Thành viên 2)
- [ ] Document staging process (Owner: Thành viên 4)
- [ ] Schedule postmortem meeting (Owner: Nhóm trưởng)

---

## Postmortem template

**Date:** ___  
**Incident ID:** ___  
**Duration:** ___ minutes  
**Impact:** ___ users affected

**Timeline:**
- T+0: ...
- T+5: ...

**Root cause:** ...

**What went well:** ...

**What went wrong:** ...

**Action items:** (link to Prevention section above)
