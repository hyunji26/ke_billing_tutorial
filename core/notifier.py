"""
알림 발송 모듈
"""

import requests
from typing import Optional

from core.anomaly_detector import AnomalyRecord


def send_slack_alert(
    anomaly: AnomalyRecord,
    webhook_url: str,
    timeout: int = 5
) -> bool:
    """
    Slack Webhook을 통해 이상치 알림을 발송합니다.
    
    Args:
        anomaly: 이상치 기록
        webhook_url: Slack Webhook URL
        timeout: 요청 타임아웃 (초)
    
    Returns:
        발송 성공 여부
    """
    if not webhook_url or not webhook_url.strip():
        return False
    
    try:
        # Slack 메시지 구성
        text = (
            f"🚨 *Billing Anomaly Detected*\n\n"
            f"*Date/Time:* {anomaly.date} {anomaly.hour:02d}:00\n"
            f"*Domain:* {anomaly.domain_name} ({anomaly.domain_id[:8]}...)\n"
            f"*Project:* {anomaly.project_name} ({anomaly.project_id[:8]}...)\n"
            f"*Service:* {anomaly.service_name} ({anomaly.service_id})\n\n"
            f"*Observed Amount:* {anomaly.observed_amount:,.2f}\n"
            f"*Baseline Mean:* {anomaly.baseline_mean:,.2f}\n"
            f"*Z-Score:* {anomaly.z_score:.2f}\n"
            f"*Deviation Ratio:* {anomaly.deviation_ratio:.2f}x\n\n"
            f"*Threshold:* Z-Score >= {anomaly.threshold_z} or Ratio >= {anomaly.threshold_ratio}x"
        )
        
        payload = {"text": text}
        
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        return True
    
    except Exception as e:
        print(f"⚠️ Slack 알림 발송 실패: {e}")
        return False

