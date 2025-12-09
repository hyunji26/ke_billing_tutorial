"""
Kakao Cloud Billing API 클라이언트 모듈
"""

import requests
from typing import Dict, Any

from config.settings import BillingApiSettings

API_URL = "https://billing-api.kakaocloud.com/open/billing/public/v2/cost/resources"


def fetch_billing(
    from_date: str,
    to_date: str,
    settings: BillingApiSettings
) -> Dict[str, Any]:
    """
    Billing API를 호출하여 비용 데이터를 가져옵니다.
    
    Args:
        from_date: 시작 날짜 (YYYYMMDD 형식)
        to_date: 종료 날짜 (YYYYMMDD 형식)
        settings: Billing API 설정 (credential_id, credential_secret)
    
    Returns:
        API 응답 JSON (dict)
    
    Raises:
        requests.exceptions.RequestException: API 호출 실패 시
    """
    params = {
        "from": from_date,
        "to": to_date,
        "size": 10000  # 항상 최대 사이즈로 호출
    }
    
    headers = {
        "Credential-ID": settings.credential_id,
        "Credential-Secret": settings.credential_secret
    }
    
    try:
        response = requests.get(API_URL, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        # 에러 메시지에 응답 내용 포함
        error_msg = f"Billing API 호출 실패: {e}"
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f"\n응답 내용: {e.response.text}"
        raise RuntimeError(error_msg) from e

