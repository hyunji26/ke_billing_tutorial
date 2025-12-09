"""
Baseline 계산 및 조회 모듈
"""

from dataclasses import dataclass
from typing import Optional, List, Set
from pymongo.collection import Collection
import statistics
import math

from infra.mongo_client import (
    get_all_daily_for_service,
    upsert_baseline
)


def percentile(data: List[float], p: float) -> float:
    """백분위수 계산 (Numpy 대체)"""
    if not data:
        return 0.0
    data.sort()
    k = (len(data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data[int(k)]
    d0 = data[int(f)]
    d1 = data[int(c)]
    return d0 + (d1 - d0) * (k - f)



@dataclass
class Baseline:
    """Baseline 통계 정보"""
    mean: float
    std: float
    min: float
    max: float
    p50: float
    p95: float
    sample_count: int


def get_baseline_data(
    collection: Collection,
    domain_id: str,
    project_id: str,
    service_id: str
) -> Optional[Baseline]:
    """
    Baseline 통계 데이터를 조회합니다.
    
    Args:
        collection: billing_baseline 컬렉션
        domain_id: 도메인 ID
        project_id: 프로젝트 ID
        service_id: 서비스 ID
    
    Returns:
        Baseline 객체 (없으면 None)
    """
    doc = collection.find_one({
        "domainId": domain_id,
        "projectId": project_id,
        "serviceId": service_id
    })
    
    if not doc:
        return None
    
    stats = doc.get("statistics", {})
    return Baseline(
        mean=stats.get("mean", 0.0),
        std=stats.get("std", 0.0),
        min=stats.get("min", 0.0),
        max=stats.get("max", 0.0),
        p50=stats.get("p50", 0.0),
        p95=stats.get("p95", 0.0),
        sample_count=stats.get("sampleCount", 0)
    )


def recompute_baseline(
    daily_collection: Collection,
    baseline_collection: Collection,
    domain_id: str,
    project_id: str,
    service_id: str,
    service_name: str
) -> None:
    """
    billing_daily의 전체 데이터를 기반으로 baseline 통계를 재계산합니다.
    
    Args:
        daily_collection: billing_daily 컬렉션
        baseline_collection: billing_baseline 컬렉션
        domain_id: 도메인 ID
        project_id: 프로젝트 ID
        service_id: 서비스 ID
        service_name: 서비스 이름
    """
    # billing_daily에서 해당 서비스의 모든 데이터 조회
    daily_docs = get_all_daily_for_service(
        daily_collection,
        domain_id,
        project_id,
        service_id
    )
    
    if not daily_docs:
        return
    
    # expectAmount 값 추출 및 pricingTypes 수집
    amounts = []
    pricing_types_set = set()

    for doc in daily_docs:
        amounts.append(float(doc.get("expectAmount") or 0))
        
        # pricingTypes 수집
        p_types = doc.get("pricingTypes", [])
        if isinstance(p_types, list):
            pricing_types_set.update(p_types)
    
    if not amounts:
        return
    
    # 통계값 계산
    mean_val = statistics.mean(amounts)
    
    # 표준편차 계산 (샘플이 2개 이상일 때만)
    if len(amounts) > 1:
        std_val = statistics.stdev(amounts)
    else:
        std_val = 0.0
    
    # 최소/최대
    min_val = min(amounts)
    max_val = max(amounts)
    
    # 백분위수 계산
    p50 = percentile(amounts, 50)
    p95 = percentile(amounts, 95)
    
    # statistics dict 구성
    statistics_dict = {
        "mean": mean_val,
        "std": std_val,
        "min": min_val,
        "max": max_val,
        "p50": p50,
        "p95": p95,
        "sampleCount": len(amounts)
    }
    
    # pricingTypes 리스트 변환 (정렬)
    pricing_types_list = sorted(list(pricing_types_set))
    
    # baseline 업데이트
    upsert_baseline(
        baseline_collection,
        domain_id,
        project_id,
        service_id,
        service_name,
        statistics_dict,
        pricing_types=pricing_types_list
    )

