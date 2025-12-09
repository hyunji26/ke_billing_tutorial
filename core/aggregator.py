"""
비용 데이터 집계 모듈
"""

from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class DailySummary:
    """일별 집계 결과"""
    metering_date: str  # YYYYMMDD
    domain_id: str
    domain_name: str
    project_id: str
    project_name: str
    service_id: str
    service_name: str
    usage_time: float
    usage_size: float
    general_amount: float
    discount_amount: float
    expect_amount: float
    pricing_types: List[str]
    regions: List[str]


def extract_entries(data: Any) -> List[Dict[str, Any]]:
    """
    API 응답에서 실제 비용 데이터 리스트를 추출합니다.
    
    Args:
        data: API 응답 (dict, result.content 형태)
    
    Returns:
        비용 엔트리 리스트
    """
    if not isinstance(data, dict):
        return []
    
    result = data.get("result")
    if not isinstance(result, dict):
        return []
    
    content = result.get("content")
    if isinstance(content, list):
        return content
    
    return []


def aggregate_daily(entries: List[Dict[str, Any]]) -> List[DailySummary]:
    """
    엔트리 리스트를 일별·도메인·프로젝트·서비스 단위로 집계합니다.
    
    Args:
        entries: 비용 엔트리 리스트
    
    Returns:
        일별 집계 결과 리스트
    """
    if not entries:
        return []
    
    # 집계 키: meteringDate|domainId|projectId|serviceId
    aggregated: Dict[str, Dict[str, Any]] = {}
    
    for item in entries:
        if not isinstance(item, dict):
            continue
        
        metering_date = item.get("meteringDate", "")
        domain_id = item.get("domainId", "")
        project_id = item.get("projectId", "")
        service_id = item.get("serviceId", "")
        
        key = "|".join([
            str(metering_date),
            str(domain_id),
            str(project_id),
            str(service_id)
        ])
        
        if key not in aggregated:
            aggregated[key] = {
                "meteringDate": metering_date,
                "domainId": domain_id,
                "domainName": item.get("domainName", ""),
                "projectId": project_id,
                "projectName": item.get("projectName", ""),
                "serviceId": service_id,
                "serviceName": item.get("serviceName", ""),
                "usageTime": 0.0,
                "usageSize": 0.0,
                "generalAmount": 0.0,
                "discountAmount": 0.0,
                "expectAmount": 0.0,
                "pricingTypes": set(),
                "regions": set()
            }
        
        entry = aggregated[key]
        entry["usageTime"] += float(item.get("usageTime") or 0)
        entry["usageSize"] += float(item.get("usageSize") or 0)
        entry["generalAmount"] += float(item.get("generalAmount") or 0)
        entry["discountAmount"] += float(item.get("discountAmount") or 0)
        entry["expectAmount"] += float(item.get("expectAmount") or 0)
        
        pricing_type = item.get("pricingType")
        region = item.get("region")
        if pricing_type:
            entry["pricingTypes"].add(pricing_type)
        if region:
            entry["regions"].add(region)
    
    # DailySummary 객체로 변환
    summaries = []
    for entry in aggregated.values():
        summaries.append(DailySummary(
            metering_date=entry["meteringDate"],
            domain_id=entry["domainId"],
            domain_name=entry["domainName"],
            project_id=entry["projectId"],
            project_name=entry["projectName"],
            service_id=entry["serviceId"],
            service_name=entry["serviceName"],
            usage_time=entry["usageTime"],
            usage_size=entry["usageSize"],
            general_amount=entry["generalAmount"],
            discount_amount=entry["discountAmount"],
            expect_amount=entry["expectAmount"],
            pricing_types=sorted(entry["pricingTypes"]),
            regions=sorted(entry["regions"])
        ))
    
    # 정렬: 날짜, 도메인, 프로젝트, 서비스 순
    summaries.sort(key=lambda x: (
        x.metering_date,
        x.domain_name,
        x.project_name,
        x.service_name
    ))
    
    return summaries

