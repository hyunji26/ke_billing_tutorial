"""
이상치 탐지 모듈
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.aggregator import DailySummary
from core.baseline import Baseline


@dataclass
class AnomalyRecord:
    """이상치 기록"""
    date: str  # YYYYMMDD
    hour: int  # 0-23
    domain_id: str
    domain_name: str
    project_id: str
    project_name: str
    service_id: str
    service_name: str
    observed_amount: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    deviation_ratio: float
    threshold_z: float
    threshold_ratio: float


def calculate_z_score(observed: float, mean: float, std: float) -> float:
    """
    Z-score를 계산합니다.
    
    Args:
        observed: 관측값
        mean: 평균
        std: 표준편차
    
    Returns:
        Z-score
    """
    if std == 0.0:
        # 표준편차가 0이면 평균과 같으면 0, 다르면 무한대
        return 0.0 if observed == mean else float('inf')
    return (observed - mean) / std


def calculate_deviation_ratio(observed: float, mean: float) -> float:
    """
    Deviation ratio를 계산합니다 (관측값 / 평균).
    
    Args:
        observed: 관측값
        mean: 평균
    
    Returns:
        Deviation ratio
    """
    if mean == 0.0:
        return 0.0 if observed == 0.0 else float('inf')
    return observed / mean 


def detect_anomalies(
    summaries: List[DailySummary],
    baseline_map: Dict[str, Baseline],
    current_date: str,
    current_hour: int,
    z_threshold: float = 3.0,
    ratio_threshold: float = 2.0
) -> List[AnomalyRecord]:
    """
    현재 집계 데이터와 baseline을 비교하여 이상치를 탐지합니다.
    
    Args:
        summaries: 현재 시간의 집계 결과 리스트
        baseline_map: Baseline 딕셔너리 (키: "domainId|projectId|serviceId")
        current_date: 현재 날짜 (YYYYMMDD)
        current_hour: 현재 시간 (0-23)
        z_threshold: Z-score 임계값 (기본값: 3.0)
        ratio_threshold: Deviation ratio 임계값 (기본값: 2.0)
    
    Returns:
        이상치 리스트
    """
    anomalies = []
    
    # 현재 시각 기준 진행률(하루 24시간 기준)
    # 예) 0시 -> 1/24, 11시 -> 12/24, 23시 -> 24/24 = 1.0
    progress = (current_hour + 1) / 24.0
    
    for summary in summaries:
        # Baseline 키 생성
        baseline_key = "|".join([
            summary.domain_id,
            summary.project_id,
            summary.service_id
        ])
        
        baseline = baseline_map.get(baseline_key)
        
        # Baseline이 없거나 샘플이 부족하면 스킵
        if not baseline or baseline.sample_count < 5:
            continue

        observed = summary.expect_amount

        # 현재 시점까지의 "정상적인 누적 기대값" 및 보정된 표준편차 계산
        # Baseline(mean, std)은 "하루 총합" 기준이므로,
        # progress를 곱해 현재 시각까지의 기대 누적값으로 보정한다.
        expected_mean = baseline.mean * progress
        expected_std = baseline.std * progress

        # 1) 하락 방향(관측값 < 기대값)은 이상치에서 제외
        #    "비용이 급증한 경우"만 이상치로 보려는 정책.
        if observed < expected_mean:
            continue
        
        # Z-score 계산
        z_score = calculate_z_score(observed, expected_mean, expected_std)
        
        # Deviation ratio 계산
        deviation_ratio = calculate_deviation_ratio(observed, expected_mean)

        # 2) std=0 인 baseline 은 z-score 대신 ratio 기준만 사용
        #    표준편차가 전혀 없다는 것은 과거 값이 거의 고정이었다는 뜻이므로,
        #    사소한 변화까지 모두 z-score 무한대로 보는 대신,
        #    "의미 있는 증가(ratio 임계치 초과)"만 이상치로 취급한다.
        if baseline.std == 0.0:
            is_anomaly = deviation_ratio >= ratio_threshold
        else:
            # 상승 방향만 보므로 z_score는 양수만 체크
            is_anomaly = (
                z_score >= z_threshold or
                deviation_ratio >= ratio_threshold
            )
        
        if is_anomaly:
            anomalies.append(AnomalyRecord(
                date=current_date,
                hour=current_hour,
                domain_id=summary.domain_id,
                domain_name=summary.domain_name,
                project_id=summary.project_id,
                project_name=summary.project_name,
                service_id=summary.service_id,
                service_name=summary.service_name,
                observed_amount=observed,
                baseline_mean=baseline.mean,
                baseline_std=baseline.std,
                z_score=z_score,
                deviation_ratio=deviation_ratio,
                threshold_z=z_threshold,
                threshold_ratio=ratio_threshold
            ))
    
    return anomalies


def anomaly_to_dict(anomaly: AnomalyRecord) -> Dict[str, Any]:
    """
    AnomalyRecord를 MongoDB에 저장할 dict 형태로 변환합니다.
    
    Args:
        anomaly: AnomalyRecord 객체
    
    Returns:
        MongoDB 문서 형태의 dict
    """
    return {
        "date": anomaly.date,
        "hour": anomaly.hour,
        "domainId": anomaly.domain_id,
        "domainName": anomaly.domain_name,
        "projectId": anomaly.project_id,
        "projectName": anomaly.project_name,
        "serviceId": anomaly.service_id,
        "serviceName": anomaly.service_name,
        "observedAmount": anomaly.observed_amount,
        "baselineMean": anomaly.baseline_mean,
        "baselineStd": anomaly.baseline_std,
        "zScore": anomaly.z_score,
        "deviationRatio": anomaly.deviation_ratio,
        "threshold": {
            "zScore": anomaly.threshold_z,
            "deviationRatio": anomaly.threshold_ratio
        },
        "status": "NEW"
    }

