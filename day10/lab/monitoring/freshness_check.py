"""
Kiểm tra freshness từ manifest pipeline (SLA đơn giản theo giờ).

Sinh viên mở rộng: đọc watermark DB, so sánh với clock batch, v.v.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Cho phép "2026-04-10T08:00:00" không có timezone
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,
    now: datetime | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Trả về ("PASS" | "WARN" | "FAIL", detail dict).

    Đọc trường `latest_exported_at` hoặc max exported_at trong cleaned summary.
    
    Distinction: Đo 2 boundary (ingest + publish) nếu có trong manifest.
    """
    now = now or datetime.now(timezone.utc)
    if not manifest_path.is_file():
        return "FAIL", {"reason": "manifest_missing", "path": str(manifest_path)}

    data: Dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Check for 2-boundary freshness (Distinction feature)
    ingest_ts = data.get("ingest_timestamp")
    publish_ts = data.get("publish_timestamp")
    
    if ingest_ts and publish_ts:
        # 2-boundary mode: check both ingest and publish freshness
        ingest_dt = parse_iso(str(ingest_ts))
        publish_dt = parse_iso(str(publish_ts))
        
        if ingest_dt is None or publish_dt is None:
            return "WARN", {"reason": "invalid_timestamp_format", "manifest": data}
        
        ingest_age_hours = (now - ingest_dt).total_seconds() / 3600.0
        publish_age_hours = (now - publish_dt).total_seconds() / 3600.0
        processing_time_hours = (publish_dt - ingest_dt).total_seconds() / 3600.0
        
        detail = {
            "mode": "2-boundary",
            "ingest_timestamp": ingest_ts,
            "publish_timestamp": publish_ts,
            "ingest_age_hours": round(ingest_age_hours, 3),
            "publish_age_hours": round(publish_age_hours, 3),
            "processing_time_hours": round(processing_time_hours, 3),
            "sla_hours": sla_hours,
        }
        
        # Check both boundaries against SLA
        if publish_age_hours <= sla_hours:
            return "PASS", detail
        return "FAIL", {**detail, "reason": "publish_freshness_sla_exceeded"}
    
    # Fallback to 1-boundary mode (original behavior)
    ts_raw = data.get("latest_exported_at") or data.get("run_timestamp")
    dt = parse_iso(str(ts_raw)) if ts_raw else None
    if dt is None:
        return "WARN", {"reason": "no_timestamp_in_manifest", "manifest": data}

    age_hours = (now - dt).total_seconds() / 3600.0
    detail = {
        "mode": "1-boundary",
        "latest_exported_at": ts_raw,
        "age_hours": round(age_hours, 3),
        "sla_hours": sla_hours,
    }
    if age_hours <= sla_hours:
        return "PASS", detail
    return "FAIL", {**detail, "reason": "freshness_sla_exceeded"}
