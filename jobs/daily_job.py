#!/usr/bin/env python3
"""
Daily Job: 매일 1회 실행되는 Billing 데이터 최종 저장 및 Baseline 업데이트
"""

import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, Tuple
from zoneinfo import ZoneInfo

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import load_settings, Settings
from core.billing_client import fetch_billing
from core.aggregator import extract_entries, aggregate_daily
from core.baseline import recompute_baseline
from core.logger import get_logger
from infra.mongo_client import (
    get_mongo_client,
    get_database,
    ensure_indexes,
    bulk_upsert_daily_summaries
)
from infra.object_storage import upload_json_with_metadata

KST = ZoneInfo("Asia/Seoul")
BILLING_DAILY_TOTAL = "BILLING_DAILY_TOTAL"


def get_target_date(offset_days: int = -1) -> str:
    """
    처리할 대상 날짜를 반환합니다. (기준: KST)
    
    Args:
        offset_days: 오늘 기준으로 며칠 전인지 (기본값: -1, 즉 어제)
    
    Returns:
        날짜 문자열 (YYYYMMDD 형식)
    """
    target = datetime.now(KST) + timedelta(days=offset_days)
    return target.strftime("%Y%m%d")

def format_yyyymmdd(date_str: str) -> str:
    """
    YYYYMMDD -> YYYY-MM-DD 포맷으로 변환합니다.
    """
    if not date_str or len(date_str) != 8:
        return date_str
    return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"


def extract_unique_services(summaries) -> Set[Tuple[str, str, str, str]]:
    """
    집계 결과에서 고유한 서비스 목록을 추출합니다.
    
    Args:
        summaries: DailySummary 리스트
    
    Returns:
        (domain_id, project_id, service_id, service_name) 튜플의 Set
    """
    services = set()
    for summary in summaries:
        services.add((
            summary.domain_id,
            summary.project_id,
            summary.service_id,
            summary.service_name
        ))
    return services 


def run_daily_job(settings: Settings, target_date: str = None):
    """
    Daily Job을 실행합니다.
    
    Args:
        settings: 설정 객체
        target_date: 대상 날짜 (YYYYMMDD), None이면 어제
    """
    if target_date is None:
        target_date = get_target_date(offset_days=-1)  # 어제 날짜

    logger = get_logger()
    
    print("=" * 60)
    print(f"📅 Daily Job 실행 - {target_date}")
    print("=" * 60)
    
    try:
        # 1. API 호출
        print("\n[1/5] Billing API 호출 중...")
        response = fetch_billing(
            from_date=target_date,
            to_date=target_date,
            settings=settings.billing_api
        )
        print(f"✅ API 호출 성공")
        
        # 2. Object Storage에 Raw 데이터 저장
        print("\n[2/5] Object Storage에 Raw 데이터 저장 중...")
        metadata = {
            "fetchedAt": datetime.utcnow().isoformat(),
            "apiParams": {
                "from": target_date,
                "to": target_date
            }
        }
        storage_path = upload_json_with_metadata(
            data=response,
            date_str=target_date,
            settings=settings.object_storage,
            metadata=metadata
        )
        print(f"✅ Raw 데이터 저장 완료: {storage_path}")
        
        # 3. Entries 추출 및 집계
        print("\n[3/5] 데이터 집계 중...")
        entries = extract_entries(response)
        print(f"✅ {len(entries)}개 엔트리 추출")
        
        if not entries:
            print("⚠️ 처리할 데이터가 없습니다.")
            return
        
        summaries = aggregate_daily(entries)
        print(f"✅ {len(summaries)}개 서비스별 집계 완료")
        
        # 4. MongoDB 연결 및 일별 데이터 저장 (Bulk Upsert)
        print("\n[4/5] MongoDB에 일별 집계 데이터 저장 중...")
        client = get_mongo_client(settings.mongo)
        db = get_database(client, settings.mongo.db_name)
        ensure_indexes(db)

        daily_col = db.billing_daily
        saved_count = bulk_upsert_daily_summaries(daily_col, summaries)
        print(f"✅ {saved_count}개 일별 집계 데이터 저장 완료")
        
        # 5. Baseline 업데이트 (각 서비스별로)
        print("\n[5/5] Baseline 업데이트 중...")
        baseline_col = db.billing_baseline
        
        unique_services = extract_unique_services(summaries)
        baseline_updated = 0
        
        for domain_id, project_id, service_id, service_name in unique_services:
            recompute_baseline(
                daily_collection=daily_col,
                baseline_collection=baseline_col,
                domain_id=domain_id,
                project_id=project_id,
                service_id=service_id,
                service_name=service_name
            )
            baseline_updated += 1
        
        print(f"✅ {baseline_updated}개 서비스 Baseline 업데이트 완료")

        # 6. Alert Center 연동용: 일별 총 요금 로그 기록 (키워드 기반)
        # - Alert Center에서 Syslog(/var/log/syslog) 수집 + 키워드 필터로 알림을 만들 수 있습니다.
        total_expect_amount = sum(s.expect_amount for s in summaries)
        date_label = format_yyyymmdd(target_date)
        log_message = (
            f"[{BILLING_DAILY_TOTAL}] "
            f"[{date_label}]의 총 요금은 {total_expect_amount:,.2f}원 입니다."
        )
        logger.info(log_message)
        print("✅ 일별 총 요금 로그 전송 완료 (Alert Center 연동용)")
        
        print("\n" + "=" * 60)
        print("✅ Daily Job 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='Billing Daily Job')
    parser.add_argument(
        '--config',
        type=str,
        default='config/settings.yaml',
        help='설정 파일 경로'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='대상 날짜 (YYYYMMDD, 기본값: 어제)'
    )
    parser.add_argument(
        '--today',
        action='store_true',
        help='오늘 날짜로 처리 (기본값: 어제)'
    )
    
    args = parser.parse_args()
    
    # 설정 로드
    settings = load_settings(args.config)
    
    # 대상 날짜 결정
    target_date = args.date
    if target_date is None:
        if args.today:
            target_date = get_target_date(offset_days=0)
        else:
            target_date = None  # 기본값(어제) 사용
    
    # Job 실행
    run_daily_job(settings, target_date)


if __name__ == "__main__":
    main()

