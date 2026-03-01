"""넥슨 메이플스토리 API 클라이언트 단위 테스트 (mock HTTP)."""
import pytest
from unittest.mock import MagicMock, patch

from app.nexon.client import NexonMapleClient, NexonMapleClientError


@pytest.fixture
def mock_httpx_client():
    """httpx.Client를 mock하여 실제 API 호출 없이 테스트."""
    with patch("app.nexon.client.httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.get = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture
def nexon_client(mock_httpx_client):
    """NexonMapleClient 인스턴스 (httpx.Client 패치로 mock 사용)."""
    with patch("app.nexon.client.settings") as mock_settings:
        mock_settings.nexon_open_api_key = "test_api_key"
        client = NexonMapleClient(api_key="test_api_key")
        # 패치로 인해 client._client는 이미 mock_cls.return_value
        yield client


def test_get_ocid_success(nexon_client, mock_httpx_client):
    """캐릭터명으로 OCID 조회 성공."""
    mock_httpx_client.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"ocid": "abc123"},
    )
    ocid = nexon_client.get_ocid("테스트캐릭터")
    assert ocid == "abc123"
    mock_httpx_client.get.assert_called_once()


def test_get_ocid_not_found(nexon_client, mock_httpx_client):
    """캐릭터 없을 때 NexonMapleClientError."""
    mock_httpx_client.get.return_value = MagicMock(status_code=404)
    with pytest.raises(NexonMapleClientError, match="찾을 수 없습니다"):
        nexon_client.get_ocid("없는캐릭터")


def test_get_ocid_empty_name(nexon_client):
    """캐릭터명 비어 있으면 NexonMapleClientError."""
    with pytest.raises(NexonMapleClientError, match="비어 있습니다"):
        nexon_client.get_ocid("   ")


def test_client_requires_api_key():
    """API 키 없으면 ValueError."""
    with patch("app.nexon.client.settings") as mock_settings:
        mock_settings.nexon_open_api_key = ""
        with pytest.raises(ValueError, match="API key is required"):
            NexonMapleClient()
