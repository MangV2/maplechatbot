"""넥슨 Open API 메이플스토리 캐릭터 조회 클라이언트.

공식 문서: https://openapi.nexon.com/ko/game/maplestory/
헤더: x-nxopen-api-key
date 미입력 시 API가 요청 시점 기준으로 조회함.
"""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://open.api.nexon.com"
MAPLE_V1 = "/maplestory/v1"


class NexonMapleClientError(Exception):
    """넥슨 API 호출 실패 (캐릭터 없음, 키 오류 등)."""
    pass


class NexonMapleClient:
    """메이플스토리 캐릭터 정보 조회 (OCID → 기본/스탯/장비 등)."""

    def __init__(self, api_key: str | None = None):
        self._key = (api_key or settings.nexon_open_api_key).strip()
        if not self._key:
            raise ValueError("Nexon Open API key is required (NEXON_OPEN_API_KEY)")
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"x-nxopen-api-key": self._key},
            timeout=15.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NexonMapleClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        resp = self._client.get(path, params=params or {})
        if resp.status_code == 404:
            raise NexonMapleClientError("캐릭터를 찾을 수 없습니다.")
        if resp.status_code == 401:
            raise NexonMapleClientError("API 키가 올바르지 않습니다.")
        resp.raise_for_status()
        data = resp.json()
        return data

    def get_ocid(self, character_name: str) -> str:
        """캐릭터명으로 OCID 조회. 없으면 NexonMapleClientError."""
        name = character_name.strip()
        if not name:
            raise NexonMapleClientError("캐릭터명이 비어 있습니다.")
        data = self._get(f"{MAPLE_V1}/id", params={"character_name": name})
        ocid = data.get("ocid")
        if not ocid:
            raise NexonMapleClientError("캐릭터를 찾을 수 없습니다.")
        return ocid

    def get_character_basic(self, ocid: str) -> dict[str, Any]:
        """캐릭터 기본 정보 (레벨, 직업, 유니온 등)."""
        return self._get(f"{MAPLE_V1}/character/basic", params={"ocid": ocid})

    def get_character_stat(self, ocid: str) -> dict[str, Any]:
        """캐릭터 스탯 (주스탯, 전투력 등 API 제공 시)."""
        return self._get(f"{MAPLE_V1}/character/stat", params={"ocid": ocid})

    def get_character_item_equipment(self, ocid: str) -> dict[str, Any]:
        """장비 착용 정보."""
        return self._get(f"{MAPLE_V1}/character/item-equipment", params={"ocid": ocid})

    def fetch_full_snapshot(self, character_name: str) -> dict[str, Any]:
        """캐릭터명 → OCID → 기본/스탯/장비 수집 후 하나의 스냅샷 dict 반환."""
        ocid = self.get_ocid(character_name)
        snapshot: dict[str, Any] = {"ocid": ocid, "character_name": character_name.strip()}

        try:
            snapshot["basic"] = self.get_character_basic(ocid)
        except Exception as e:
            logger.warning("character/basic 조회 실패: %s", e)
            snapshot["basic"] = {}

        try:
            snapshot["stat"] = self.get_character_stat(ocid)
        except Exception as e:
            logger.warning("character/stat 조회 실패: %s", e)
            snapshot["stat"] = {}

        try:
            snapshot["item_equipment"] = self.get_character_item_equipment(ocid)
        except Exception as e:
            logger.warning("character/item-equipment 조회 실패: %s", e)
            snapshot["item_equipment"] = {}

        return snapshot
