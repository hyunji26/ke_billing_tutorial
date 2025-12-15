"""
Kakao Cloud Billing API 클라이언트 모듈
"""

import requests
import time
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
    headers = {
        "Credential-ID": settings.credential_id,
        "Credential-Secret": settings.credential_secret
    }
    
    # 문서 기준: page(0부터), size(max 10000)
    page = 0
    size = 10000
    contents = []

    try:
        while True:
            params = {
                "from": from_date,
                "to": to_date,
                "page": page,
                "size": size
            }

            # 429 등 일시 오류에 대한 최소한의 재시도 (운영 안전장치)
            last_exc = None
            for attempt in range(5):
                try:
                    response = requests.get(API_URL, params=params, headers=headers, timeout=60)
                    if response.status_code == 429:
                        time.sleep(min(2 ** attempt, 10))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    break
                except requests.exceptions.RequestException as e:
                    last_exc = e
                    time.sleep(min(2 ** attempt, 10))
            else:
                raise last_exc  # type: ignore[misc]

            result = data.get("result") if isinstance(data, dict) else None
            content = result.get("content") if isinstance(result, dict) else None
            if not isinstance(content, list):
                # 예상 포맷이 아니면 그대로 반환 (상위에서 예외 처리 가능)
                return data

            contents.extend(content)

            # 마지막 페이지 판단: 받은 개수가 size보다 작으면 끝
            if len(content) < size:
                # content를 누적한 형태로 응답을 재구성해서 반환
                if isinstance(data, dict):
                    data.setdefault("result", {})
                    if isinstance(data["result"], dict):
                        data["result"]["content"] = contents
                return data

            page += 1

            # 안전장치: 무한 루프 방지 (10,000 * 1000 = 1천만 rows)
            if page > 1000:
                raise RuntimeError("Billing API paging exceeded max pages (1000). Possible infinite paging.")
    except requests.exceptions.RequestException as e:
        # 에러 메시지에 응답 내용 포함
        error_msg = f"Billing API 호출 실패: {e}"
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f"\n응답 내용: {e.response.text}"
        raise RuntimeError(error_msg) from e

