"""캐릭터 스냅샷 요약 문자열 생성 (노드 공통)."""
from typing import Any


def snapshot_summary(snapshot: dict[str, Any] | None) -> str:
    """스냅샷에서 레벨·직업·스탯·장비 요약 텍스트 생성. 없으면 빈 문자열."""
    if not snapshot:
        return ""
    parts: list[str] = []

    basic = snapshot.get("basic") or {}
    if isinstance(basic, dict):
        level = basic.get("level") or basic.get("character_level")
        job = basic.get("character_class") or basic.get("job") or basic.get("character_class_name")
        if level is not None:
            parts.append(f"레벨: {level}")
        if job:
            parts.append(f"직업: {job}")

    stat = snapshot.get("stat") or {}
    if isinstance(stat, dict):
        # API가 final_stat 리스트로 오는 경우 등
        final_stat = stat.get("final_stat")
        if isinstance(final_stat, list):
            for s in final_stat[:10]:
                if isinstance(s, dict) and s.get("stat_name") and s.get("stat_value"):
                    parts.append(f"{s.get('stat_name')}: {s.get('stat_value')}")
        elif isinstance(stat, dict) and stat.get("attack_power"):
            parts.append(f"공격력: {stat.get('attack_power')}")

    item_eq = snapshot.get("item_equipment") or {}
    if isinstance(item_eq, dict):
        items = item_eq.get("item_equipment") or item_eq.get("item_equipment_preset_1") or []
        if isinstance(items, list) and items:
            parts.append(f"장비 슬롯 수: {len(items)}")

    return "\n".join(parts) if parts else ""


def get_level_from_snapshot(snapshot: dict[str, Any] | None) -> int | None:
    """스냅샷에서 레벨 추출. 없으면 None."""
    if not snapshot:
        return None
    basic = snapshot.get("basic") or {}
    if isinstance(basic, dict):
        level = basic.get("level") or basic.get("character_level")
        if level is not None:
            try:
                return int(level)
            except (TypeError, ValueError):
                pass
    return None


def get_combat_power_from_snapshot(snapshot: dict[str, Any] | None) -> int | None:
    """스냅샷에서 전투력 추출 (넥슨 API stat.final_stat 기준). 없으면 None."""
    if not snapshot:
        return None
    stat = snapshot.get("stat") or {}
    if not isinstance(stat, dict):
        return None
    final_stat = stat.get("final_stat")
    if not isinstance(final_stat, list):
        return None
    for s in final_stat:
        if isinstance(s, dict) and (s.get("stat_name") or "").strip() == "전투력":
            try:
                val = s.get("stat_value")
                if val is None:
                    continue
                return int(val)
            except (TypeError, ValueError):
                pass
    return None
