"""
MongoDB 클라이언트 및 CRUD 함수 모듈
"""

from typing import List, Optional
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import UpdateOne

from config.settings import MongoSettings
from core.aggregator import DailySummary


def get_mongo_client(settings: MongoSettings) -> MongoClient:
    """
    MongoDB 클라이언트를 생성합니다.
    
    Args:
        settings: MongoDB 설정 (uri, db_name)
    
    Returns:
        MongoClient 인스턴스
    """
    return MongoClient(settings.uri)


def get_database(client: MongoClient, db_name: str) -> Database:
    """
    데이터베이스를 가져옵니다.
    
    Args:
        client: MongoClient 인스턴스
        db_name: 데이터베이스 이름
    
    Returns:
        Database 인스턴스
    """
    return client[db_name]


def ensure_indexes(db: Database):
    """
    필요한 인덱스를 생성합니다.
    
    Args:
        db: Database 인스턴스
    """
    # billing_daily 인덱스
    db.billing_daily.create_index(
        [
            ("date", ASCENDING),
            ("domainId", ASCENDING),
            ("projectId", ASCENDING),
            ("serviceId", ASCENDING),
            ("pricingType", ASCENDING)
        ],
        unique=True,
        name="unique_daily_summary"
    )
    db.billing_daily.create_index(
        [("date", DESCENDING)],
        name="date_desc"
    )
    
    # billing_baseline 인덱스
    db.billing_baseline.create_index(
        [
            ("domainId", ASCENDING),
            ("projectId", ASCENDING),
            ("serviceId", ASCENDING),
            ("pricingType", ASCENDING)
        ],
        unique=True,
        name="unique_baseline"
    )
    
    # billing_anomalies 인덱스
    db.billing_anomalies.create_index(
        [("date", DESCENDING), ("hour", DESCENDING)],
        name="date_hour_desc"
    )
    # 동일 시간대 동일 서비스의 이상치가 반복 저장되지 않도록 유니크 키를 둡니다.
    # 이미 중복 데이터가 존재하면 unique index 생성이 실패할 수 있으므로, 잡이 죽지 않도록 보호합니다.
    try:
        db.billing_anomalies.create_index(
            [
                ("date", ASCENDING),
                ("hour", ASCENDING),
                ("domainId", ASCENDING),
                ("projectId", ASCENDING),
                ("serviceId", ASCENDING),
            ],
            unique=True,
            name="unique_anomaly_key"
        )
    except OperationFailure:
        # 기존 중복 데이터가 있는 경우 등: 인덱스 생성 실패 시에도 서비스 동작은 계속되게 둔다.
        # (이후 insert_anomaly가 upsert이므로 신규 중복은 줄어든다)
        pass
    db.billing_anomalies.create_index(
        [("status", ASCENDING), ("createdAt", DESCENDING)],
        name="status_created_desc"
    )
    db.billing_anomalies.create_index(
        [
            ("domainId", ASCENDING),
            ("projectId", ASCENDING),
            ("serviceId", ASCENDING)
        ],
        name="domain_project_service"
    )



def upsert_daily_summary(
    collection: Collection,
    summary: DailySummary
) -> None:
    """
    일별 집계 데이터를 MongoDB에 저장/업데이트합니다.
    현재 구현에서는 L1 집계(하루/서비스 단위)만 사용하므로
    pricingType 필드는 항상 None 으로 저장합니다.
    
    Args:
        collection: billing_daily 컬렉션
        summary: 일별 집계 결과
    """
    # L1 집계: pricingType 은 사용하지 않고 None 으로 고정
    filter_query = {
        "date": summary.metering_date,
        "domainId": summary.domain_id,
        "projectId": summary.project_id,
        "serviceId": summary.service_id,
        "pricingType": None
    }
    
    update_data = {
        "$set": {
            "date": summary.metering_date,
            "domainId": summary.domain_id,
            "domainName": summary.domain_name,
            "projectId": summary.project_id,
            "projectName": summary.project_name,
            "serviceId": summary.service_id,
            "serviceName": summary.service_name,
            # L1 집계만 사용하므로 pricingType 은 None
            "pricingType": None,
            "expectAmount": summary.expect_amount,
            "usageTime": summary.usage_time,
            "usageSize": summary.usage_size,
            "generalAmount": summary.general_amount,
            "discountAmount": summary.discount_amount,
            "pricingTypes": summary.pricing_types,
            "regions": summary.regions,
            "updatedAt": datetime.utcnow()
        },
        "$setOnInsert": {
            "createdAt": datetime.utcnow(),
            "isAnomaly": False  # 기본값 설정
        }
    }
    
    collection.update_one(filter_query, update_data, upsert=True)


def bulk_upsert_daily_summaries(
    collection: Collection,
    summaries: List[DailySummary]
) -> int:
    """
    여러 일별 집계 데이터를 bulk upsert로 효율적으로 저장합니다.
    
    Args:
        collection: billing_daily 컬렉션
        summaries: 일별 집계 결과 리스트
    
    Returns:
        처리된 문서 개수
    """
    if not summaries:
        return 0
    
    now = datetime.utcnow()
    operations = []
    
    for summary in summaries:
        # L1 집계: pricingType 은 사용하지 않고 None 으로 고정
        filter_query = {
            "date": summary.metering_date,
            "domainId": summary.domain_id,
            "projectId": summary.project_id,
            "serviceId": summary.service_id,
            "pricingType": None
        }
        
        update_data = {
            "$set": {
                "date": summary.metering_date,
                "domainId": summary.domain_id,
                "domainName": summary.domain_name,
                "projectId": summary.project_id,
                "projectName": summary.project_name,
                "serviceId": summary.service_id,
                "serviceName": summary.service_name,
                # L1 집계만 사용하므로 pricingType 은 None
                "pricingType": None,
                "expectAmount": summary.expect_amount,
                "usageTime": summary.usage_time,
                "usageSize": summary.usage_size,
                "generalAmount": summary.general_amount,
                "discountAmount": summary.discount_amount,
                "pricingTypes": summary.pricing_types,
                "regions": summary.regions,
                "updatedAt": now
            },
            "$setOnInsert": {
                "createdAt": now,
                "isAnomaly": False  # 기본값 설정
            }
        }
        
        operations.append(
            UpdateOne(
                filter_query,
                update_data,
                upsert=True
            )
        )
    
    if operations:
        result = collection.bulk_write(operations, ordered=False)
        return result.upserted_count + result.modified_count
    
    return 0


def get_all_daily_for_service(
    collection: Collection,
    domain_id: str,
    project_id: str,
    service_id: str,
    pricing_type: Optional[str] = None
) -> List[dict]:
    """
    특정 서비스(및 pricing_type)의 모든 일별 데이터를 조회합니다.
    
    Args:
        collection: billing_daily 컬렉션
        domain_id: 도메인 ID
        project_id: 프로젝트 ID
        service_id: 서비스 ID
        pricing_type: Pricing Type (None이면 L1 데이터 조회)
    
    Returns:
        일별 데이터 리스트
    """
    # 기본적으로는 해당 서비스의 L1/L2 일별 데이터 전체를 대상으로 하되,
    # 이상치로 마킹된(isAnomaly=True) 데이터는 baseline 계산에서 제외합니다.
    query = {
        "domainId": domain_id,
        "projectId": project_id,
        "serviceId": service_id,
        "isAnomaly": {"$ne": True}
    }

    # 특정 pricing_type 으로 L2만 보고 싶을 때만 pricingType 필터를 추가
    if pricing_type is not None:
        query["pricingType"] = pricing_type

    # billing_daily 에서 조건에 맞는 모든 문서를 날짜 기준 오름차순으로 조회
    cursor = collection.find(query).sort("date", ASCENDING)
    return list(cursor)


def update_daily_anomaly_status(
    collection: Collection,
    date: str,
    domain_id: str,
    project_id: str,
    service_id: str,
    is_anomaly: bool
) -> None:
    """
    일별 데이터의 이상치 상태를 업데이트합니다.
    
    Args:
        collection: billing_daily 컬렉션
        date: 날짜 (YYYYMMDD)
        domain_id: 도메인 ID
        project_id: 프로젝트 ID
        service_id: 서비스 ID
        is_anomaly: 이상치 여부
    """
    filter_query = {
        "date": date,
        "domainId": domain_id,
        "projectId": project_id,
        "serviceId": service_id,
        "pricingType": None  # L1 데이터만 대상
    }
    
    update_data = {
        "$set": {
            "isAnomaly": is_anomaly,
            "updatedAt": datetime.utcnow()
        },
        "$setOnInsert": {
            "createdAt": datetime.utcnow()
        }
    }
    
    collection.update_one(filter_query, update_data, upsert=True)



def insert_anomaly(
    collection: Collection,
    anomaly_data: dict
) -> None:
    """
    이상치 데이터를 MongoDB에 저장합니다.
    
    Args:
        collection: billing_anomalies 컬렉션
        anomaly_data: 이상치 데이터 (dict)
    """
    # 동일 시간대 동일 서비스의 이상치가 여러 번(재실행/재시도) 저장되는 것을 방지하기 위해 upsert로 저장합니다.
    # 키: (date, hour, domainId, projectId, serviceId)
    filter_query = {
        "date": anomaly_data.get("date"),
        "hour": anomaly_data.get("hour"),
        "domainId": anomaly_data.get("domainId"),
        "projectId": anomaly_data.get("projectId"),
        "serviceId": anomaly_data.get("serviceId"),
    }

    now = datetime.utcnow()
    if "status" not in anomaly_data:
        anomaly_data["status"] = "NEW"

    # createdAt은 최초 insert 시에만, updatedAt은 매번 갱신
    update_doc = {
        "$set": {**anomaly_data, "updatedAt": now},
        "$setOnInsert": {"createdAt": now},
    }

    collection.update_one(filter_query, update_doc, upsert=True)


def upsert_baseline(
    collection: Collection,
    domain_id: str,
    project_id: str,
    service_id: str,
    service_name: str,
    statistics: dict,
    pricing_type: Optional[str] = None,
    pricing_types: Optional[List[str]] = None
) -> None:
    """
    Baseline 통계를 MongoDB에 저장/업데이트합니다.
    
    Args:
        collection: billing_baseline 컬렉션
        domain_id: 도메인 ID
        project_id: 프로젝트 ID
        service_id: 서비스 ID
        service_name: 서비스 이름
        statistics: 통계 데이터
        pricing_type: Pricing Type (L2 집계 키)
        pricing_types: 포함된 Pricing Type 목록 (메타데이터)
    """
    filter_query = {
        "domainId": domain_id,
        "projectId": project_id,
        "serviceId": service_id,
        "pricingType": pricing_type
    }
    
    update_data = {
        "$set": {
            "domainId": domain_id,
            "projectId": project_id,
            "serviceId": service_id,
            "serviceName": service_name,
            "pricingType": pricing_type,
            "statistics": statistics,
            "lastUpdated": datetime.utcnow()
        },
        "$setOnInsert": {
            "createdAt": datetime.utcnow()
        }
    }

    if pricing_types is not None:
        update_data["$set"]["pricingTypes"] = pricing_types
    
    collection.update_one(filter_query, update_data, upsert=True)


def get_baseline(
    collection: Collection,
    domain_id: str,
    project_id: str,
    service_id: str,
    pricing_type: Optional[str] = None
) -> Optional[dict]:
    """
    Baseline 통계를 조회합니다.
    
    Args:
        collection: billing_baseline 컬렉션
        domain_id: 도메인 ID
        project_id: 프로젝트 ID
        service_id: 서비스 ID
        pricing_type: Pricing Type
    
    Returns:
        Baseline 문서 (없으면 None)
    """
    return collection.find_one({
        "domainId": domain_id,
        "projectId": project_id,
        "serviceId": service_id,
        "pricingType": pricing_type
    })
