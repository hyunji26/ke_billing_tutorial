"""
Object Storage 업로드 모듈
Kakao Cloud Object Storage (S3 호환) 연동
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

from config.settings import ObjectStorageSettings


def get_s3_client(settings: ObjectStorageSettings):
    """
    S3 클라이언트를 생성합니다.
    
    Args:
        settings: Object Storage 설정
    
    Returns:
        boto3 S3 클라이언트
    """
    return boto3.client(
        's3',
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name='kr-standard'  # Kakao Cloud 기본 리전
    )


def upload_json(
    data: Dict[str, Any],
    date_str: str,
    settings: ObjectStorageSettings
) -> str:
    """
    JSON 데이터를 Kakao Cloud Object Storage에 업로드합니다.
    
    Args:
        data: 저장할 JSON 데이터
        date_str: 날짜 문자열 (YYYYMMDD)
        settings: Object Storage 설정
    
    Returns:
        Object Storage key (경로)
    
    Raises:
        ClientError: 업로드 실패 시
    """
    year = date_str[:4]
    month = date_str[4:6]
    day = date_str[6:8]
    
    # Object Storage key 구조: raw/year=YYYY/month=MM/day=DD/billing_YYYYMMDD.json
    key = f"raw/year={year}/month={month}/day={day}/billing_{date_str}.json"
    
    # JSON을 문자열로 변환
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    json_bytes = json_str.encode('utf-8')
    
    # S3 클라이언트 생성 및 업로드
    s3_client = get_s3_client(settings)
    
    try:
        s3_client.put_object(
            Bucket=settings.bucket,
            Key=key,
            Body=json_bytes,
            ContentType='application/json',
            ContentEncoding='utf-8'
        )
        return key
    except ClientError as e:
        raise RuntimeError(f"Object Storage 업로드 실패: {e}") from e


def upload_json_with_metadata(
    data: Dict[str, Any],
    date_str: str,
    settings: ObjectStorageSettings,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    메타데이터를 포함하여 JSON 데이터를 업로드합니다.
    
    Args:
        data: 저장할 JSON 데이터
        date_str: 날짜 문자열 (YYYYMMDD)
        settings: Object Storage 설정
        metadata: 추가 메타데이터 (fetchedAt, jobId 등)
    
    Returns:
        Object Storage key (경로)
    """
    # 메타데이터 추가
    if metadata:
        data_with_meta = {
            **data,
            "_metadata": {
                **metadata,
                "uploadedAt": datetime.utcnow().isoformat()
            }
        }
    else:
        data_with_meta = {
            **data,
            "_metadata": {
                "uploadedAt": datetime.utcnow().isoformat()
            }
        }
    
    return upload_json(data_with_meta, date_str, settings)


def check_bucket_exists(settings: ObjectStorageSettings) -> bool:
    """
    버킷이 존재하는지 확인합니다.
    
    Args:
        settings: Object Storage 설정
    
    Returns:
        버킷 존재 여부
    """
    try:
        s3_client = get_s3_client(settings)
        s3_client.head_bucket(Bucket=settings.bucket)
        return True
    except ClientError:
        return False
