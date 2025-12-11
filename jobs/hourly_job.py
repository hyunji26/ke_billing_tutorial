#!/usr/bin/env python3
"""
Hourly Job: 매 시간마다 실행되는 Billing 데이터 수집 및 이상치 탐지
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import load_settings, Settings
from core.billing_client import fetch_billing
from core.aggregator import extract_entries, aggregate_daily
from core.baseline import get_baseline_data
from core.anomaly_detector import detect_anomalies, anomaly_to_dict
from core.logger import get_logger
from infra.mongo_client import (
    get_mongo_client,
    get_database,
    ensure_indexes,
    insert_anomaly,
    update_daily_anomaly_status
)


KST = ZoneInfo("Asia/Seoul")


def get_current_target_date() -> str:
    """
    현재 (KST) 시간 기준으로 처리할 날짜를 반환합니다.
    
    Returns:
        날짜 문자열 (YYYYMMDD 형식)
    """
    now = datetime.now(KST)
    return now.strftime("%Y%m%d")


def build_baseline_map(db, summaries):
    """
    집계 결과에서 필요한 baseline들을 조회하여 map을 구성합니다.
    
    Args:
        db: MongoDB Database 인스턴스
        summaries: DailySummary 리스트
    
    Returns:
        baseline_map: {"domainId|projectId|serviceId": Baseline} 딕셔너리
    """
    baseline_map = {}
    baseline_col = db.billing_baseline
    
    # 집계된 서비스별로 baseline 조회
    seen_keys = set()
    for summary in summaries:
        key = "|".join([
            summary.domain_id,
            summary.project_id,
            summary.service_id
        ])
        
        if key not in seen_keys:
            seen_keys.add(key)
            baseline = get_baseline_data(
                baseline_col,
                summary.domain_id,
                summary.project_id,
                summary.service_id
            )
            if baseline:
                baseline_map[key] = baseline
    
    return baseline_map


def run_hourly_job(settings: Settings, target_date: str = None):
    """
    Hourly Job을 실행합니다.
    
    Args:
        settings: 설정 객체
        target_date: 대상 날짜 (YYYYMMDD), None이면 오늘
    """
    if target_date is None:
        target_date = get_current_target_date()
    
    now = datetime.now(KST)
    current_hour = now.hour
    logger = get_logger()
    
    print("=" * 60)
    print(f"🕐 Hourly Job 실행 - {target_date} {current_hour:02d}:00")
    print("=" * 60)
    
    try:
        # 1. API 호출
        print("\n[1/6] Billing API 호출 중...")
        response = fetch_billing(
            from_date=target_date,
            to_date=target_date,
            settings=settings.billing_api
        )
        print(f"✅ API 호출 성공")
        
        # 2. Entries 추출
        print("\n[2/6] Entries 추출 중...")
        entries = extract_entries(response)
        print(f"✅ {len(entries)}개 엔트리 추출")
        
        if not entries:
            print("⚠️ 처리할 데이터가 없습니다.")
            return
        
        # 3. 집계 (현재 시점까지 누적 합계)
        print("\n[3/6] 데이터 집계 중...")
        summaries = aggregate_daily(entries)
        print(f"✅ {len(summaries)}개 서비스별 집계 완료")
        
        # 4. MongoDB 연결
        print("\n[4/6] MongoDB 연결 중...")
        client = get_mongo_client(settings.mongo)
        db = get_database(client, settings.mongo.db_name)
        ensure_indexes(db)
        print("✅ MongoDB 연결 성공")
        
        # 5. Baseline 조회
        print("\n[5/6] Baseline 조회 중...")
        baseline_map = build_baseline_map(db, summaries)
        print(f"✅ {len(baseline_map)}개 Baseline 조회 완료")
        
        # 6. 이상치 탐지
        print("\n[6/6] 이상치 탐지 중...")
        anomalies = detect_anomalies(
            summaries=summaries,
            baseline_map=baseline_map,
            current_date=target_date,
            current_hour=current_hour,
            z_threshold=3.0,
            ratio_threshold=2.0
        )
        print(f"✅ {len(anomalies)}개 이상치 발견")
        
        # 7. 이상치 저장 및 알림
        if anomalies:
            anomalies_col = db.billing_anomalies
            daily_col = db.billing_daily
            
            for anomaly in anomalies:
                #1) MongoDB 저장 (이상치 이력)
                anomaly_dict = anomaly_to_dict(anomaly)
                insert_anomaly(anomalies_col, anomaly_dict)
                
                #2) 일별 집계 테이블에 이상치 마킹 (Daily Job Baseline 제외용)
                update_daily_anomaly_status(
                    collection=daily_col,
                    date=anomaly.date,
                    domain_id=anomaly.domain_id,
                    project_id=anomaly.project_id,
                    service_id=anomaly.service_id,
                    is_anomaly=True
                )
                
                #3) syslog에 이상치 로그 기록 (Alert Center 연동용)
                # 고객에게 바로 보여줄 수 있도록, 자연어 한 문장 형태로 기록합니다.
                # 예)
                # [BILLING_ANOMALY] {domainName}/{projectName} 프로젝트의 {serviceName} 비용이 평소보다 높습니다. 현재 {amount}원, 기준 평균 {baselineMean}원.
                log_message = (
                    f"[BILLING_ANOMALY] "
                    f"{anomaly.domain_name}/{anomaly.project_name} 프로젝트의 "
                    f"{anomaly.service_name} 비용이 평소보다 높습니다. "
                    f"현재 {anomaly.observed_amount:.2f}원, "
                    f"기준 평균 {anomaly.baseline_mean:.2f}원."
                )
                logger.error(log_message)
            
            print(f"\n✅ {len(anomalies)}개 이상치 저장 및 알림 발송 완료")
        else:
            print("\n✅ 이상치 없음")
        
        print("\n" + "=" * 60)
        print("✅ Hourly Job 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='Billing Hourly Job')
    parser.add_argument(
        '--config',
        type=str,
        default='config/settings.yaml',
        help='설정 파일 경로'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='대상 날짜 (YYYYMMDD, 기본값: 오늘)'
    )
    
    args = parser.parse_args()
    
    # 설정 로드
    settings = load_settings(args.config)
    
    # Job 실행
    run_hourly_job(settings, args.date)


if __name__ == "__main__":
    main()

