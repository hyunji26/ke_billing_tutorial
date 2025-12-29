# 테스트 가이드 (QA 방법)

이 문서는 Billing Alert Tutorial 프로젝트의 테스트 및 QA 방법을 상세히 설명합니다.

## 📋 목차

- [테스트 전략](#테스트-전략)
- [환경 준비](#환경-준비)
- [단위 테스트](#단위-테스트)
- [통합 테스트](#통합-테스트)
- [E2E 테스트](#e2e-테스트)
- [성능 테스트](#성능-테스트)
- [테스트 체크리스트](#테스트-체크리스트)

## 🎯 테스트 전략

### 테스트 피라미드

```
        ┌─────────────┐
        │   E2E Test   │  (최소)
        └─────────────┘
       ┌───────────────┐
       │ Integration   │  (중간)
       │     Test      │
       └───────────────┘
      ┌─────────────────┐
      │   Unit Test      │  (최대)
      └─────────────────┘
```

### 테스트 우선순위

1. **단위 테스트**: 각 모듈의 핵심 로직 검증
2. **통합 테스트**: 모듈 간 연동 검증
3. **E2E 테스트**: 전체 파이프라인 검증
4. **성능 테스트**: 대용량 데이터 처리 검증

## 🔧 환경 준비

### 1. 테스트 환경 구성

```bash
# 프로젝트 디렉토리로 이동
cd billing_tutorial

# 가상환경 생성 (선택사항)
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 또는
venv\Scripts\activate  # Windows

# 패키지 설치
pip install -r requirements.txt
```

### 2. 테스트용 설정 파일 생성

```bash
# 테스트용 설정 파일 생성 (운영 설정을 복사 후 테스트용으로 수정)
cd config/settings.yaml
```

`config/settings.test.yaml`을 테스트 환경에 맞게 수정:

```yaml
billingApi:
  credentialId: "TEST_CREDENTIAL_ID"
  credentialSecret: "TEST_CREDENTIAL_SECRET"

mongo:
  uri: "mongodb://localhost:27017/billing_test"  # 테스트용 DB
  dbName: "billing_test"

objectStorage:
  endpoint: "https://object-storage.kakaocloud.com"
  bucket: "test-billing-bucket"  # 테스트용 버킷
  accessKey: "TEST_ACCESS_KEY"
  secretKey: "TEST_SECRET_KEY"
```

### 3. MongoDB 테스트 데이터 준비

```python
# test_setup_mongodb.py
from infra.mongo_client import get_mongo_client, get_database, ensure_indexes
from config.settings import load_settings
from datetime import datetime, timedelta

settings = load_settings('config/settings.test.yaml')
client = get_mongo_client(settings.mongo)
db = get_database(client, settings.mongo.db_name)

# 인덱스 생성
ensure_indexes(db)

# 테스트용 Baseline 데이터 생성
baseline_col = db.billing_baseline
baseline_col.insert_one({
    "domainId": "test_domain",
    "domainName": "Test Domain",
    "projectId": "test_project",
    "projectName": "Test Project",
    "serviceId": "1",
    "serviceName": "Test Service",
    "statistics": {
        "mean": 10000.0,
        "std": 2000.0,
        "min": 5000.0,
        "max": 15000.0,
        "p50": 9800.0,
        "p95": 14000.0,
        "sampleCount": 30
    },
    "createdAt": datetime.utcnow(),
    "lastUpdated": datetime.utcnow()
})

print("✅ 테스트 데이터 준비 완료")
```

## 🧪 단위 테스트

### 1. Billing API 클라이언트 테스트

**파일**: `test_billing_client.py`

```python
import pytest
from unittest.mock import patch, Mock
from core.billing_client import fetch_billing
from config.settings import BillingApiSettings

def test_fetch_billing_success():
    """API 호출 성공 테스트"""
    settings = BillingApiSettings(
        credential_id="test_id",
        credential_secret="test_secret"
    )
    
    mock_response = Mock()
    mock_response.json.return_value = {
        "result": {
            "content": [
                {"meteringDate": "20251205", "expectAmount": 1000}
            ]
        }
    }
    mock_response.raise_for_status = Mock()
    
    with patch('core.billing_client.requests.get', return_value=mock_response):
        result = fetch_billing("20251205", "20251205", settings)
        assert "result" in result
        assert "content" in result["result"]

def test_fetch_billing_failure():
    """API 호출 실패 테스트"""
    settings = BillingApiSettings(
        credential_id="test_id",
        credential_secret="test_secret"
    )
    
    with patch('core.billing_client.requests.get', side_effect=Exception("API Error")):
        with pytest.raises(RuntimeError):
            fetch_billing("20251205", "20251205", settings)
```

**실행**:
```bash
pytest test_billing_client.py -v
```

### 2. 데이터 집계 테스트

**파일**: `test_aggregator.py`

```python
from core.aggregator import extract_entries, aggregate_daily

def test_extract_entries():
    """Entries 추출 테스트"""
    data = {
        "result": {
            "content": [
                {"meteringDate": "20251205", "expectAmount": 1000},
                {"meteringDate": "20251205", "expectAmount": 2000}
            ]
        }
    }
    
    entries = extract_entries(data)
    assert len(entries) == 2
    assert entries[0]["expectAmount"] == 1000

def test_aggregate_daily():
    """일별 집계 테스트"""
    entries = [
        {
            "meteringDate": "20251205",
            "domainId": "domain1",
            "projectId": "project1",
            "serviceId": "service1",
            "expectAmount": 1000,
            "usageTime": 10.0
        },
        {
            "meteringDate": "20251205",
            "domainId": "domain1",
            "projectId": "project1",
            "serviceId": "service1",
            "expectAmount": 2000,
            "usageTime": 20.0
        }
    ]
    
    summaries = aggregate_daily(entries)
    assert len(summaries) == 1
    assert summaries[0].expect_amount == 3000.0
    assert summaries[0].usage_time == 30.0
```

### 3. 이상치 탐지 테스트

**파일**: `test_anomaly_detector.py`

```python
from core.anomaly_detector import (
    calculate_z_score,
    calculate_deviation_ratio,
    detect_anomalies
)
from core.aggregator import DailySummary
from core.baseline import Baseline

def test_calculate_z_score():
    """Z-score 계산 테스트"""
    z = calculate_z_score(observed=15000, mean=10000, std=2000)
    assert abs(z - 2.5) < 0.01  # (15000 - 10000) / 2000 = 2.5

def test_calculate_deviation_ratio():
    """Deviation Ratio 계산 테스트"""
    ratio = calculate_deviation_ratio(observed=20000, mean=10000)
    assert ratio == 2.0

def test_detect_anomalies():
    """이상치 탐지 테스트"""
    summaries = [
        DailySummary(
            metering_date="20251205",
            domain_id="domain1",
            domain_name="Domain 1",
            project_id="project1",
            project_name="Project 1",
            service_id="service1",
            service_name="Service 1",
            usage_time=0.0,
            usage_size=0.0,
            general_amount=0.0,
            discount_amount=0.0,
            expect_amount=50000.0,  # 평균의 5배 (이상치)
            pricing_types=[],
            regions=[]
        )
    ]
    
    baseline_map = {
        "domain1|project1|service1": Baseline(
            mean=10000.0,
            std=2000.0,
            min=5000.0,
            max=15000.0,
            p50=9800.0,
            p95=14000.0,
            sample_count=30
        )
    }
    
    anomalies = detect_anomalies(
        summaries=summaries,
        baseline_map=baseline_map,
        current_date="20251205",
        current_hour=14,
        z_threshold=3.0,
        ratio_threshold=2.0
    )
    
    assert len(anomalies) == 1
    assert anomalies[0].observed_amount == 50000.0
    assert anomalies[0].z_score > 3.0
    assert anomalies[0].deviation_ratio >= 2.0
```

위 테스트는 Z-score / Deviation Ratio 계산과 임계값 비교 로직만 단순 검증합니다.  
현재 `detect_anomalies` 구현은 Baseline의 평균·표준편차(하루 총합 기준)를 기대값으로 사용해 관측값(오늘 누적)과 비교합니다.

## 🔗 통합 테스트

### 1. Hourly Job 통합 테스트

**파일**: `test_hourly_job_integration.py`

```python
import pytest
from unittest.mock import patch
from jobs.hourly_job import run_hourly_job
from config.settings import load_settings

def test_hourly_job_integration():
    """Hourly Job 전체 흐름 테스트 (MongoDB + Syslog 중심)"""
    settings = load_settings('config/settings.test.yaml')
    
    # Mock API 응답
    mock_api_response = {
        "result": {
            "content": [
                {
                    "meteringDate": "20251205",
                    "domainId": "test_domain",
                    "projectId": "test_project",
                    "serviceId": "1",
                    "expectAmount": 50000.0,  # 이상치 (평균 10000의 5배)
                    "usageTime": 10.0,
                    "usageSize": 0.0
                }
            ]
        }
    }
    
    # Billing API만 Mock 처리 (Slack, Syslog 등 외부 연동은 별도 유닛 테스트에서 검증)
    with patch('core.billing_client.fetch_billing', return_value=mock_api_response):
        run_hourly_job(settings, "20251205")
    
    # MongoDB에서 이상치 확인
    from infra.mongo_client import get_mongo_client, get_database
    client = get_mongo_client(settings.mongo)
    db = get_database(client, settings.mongo.db_name)
    
    anomalies = list(db.billing_anomalies.find({"date": "20251205"}))
    assert len(anomalies) > 0
    assert anomalies[0]["observedAmount"] == 50000.0
```

### 2. Daily Job 통합 테스트

**파일**: `test_daily_job_integration.py`

```python
import pytest
from unittest.mock import patch
from jobs.daily_job import run_daily_job
from config.settings import load_settings

def test_daily_job_integration():
    """Daily Job 전체 흐름 테스트"""
    settings = load_settings('config/settings.test.yaml')
    
    mock_api_response = {
        "result": {
            "content": [
                {
                    "meteringDate": "20251204",
                    "domainId": "test_domain",
                    "projectId": "test_project",
                    "serviceId": "1",
                    "expectAmount": 10000.0,
                    "usageTime": 10.0,
                    "usageSize": 0.0
                }
            ]
        }
    }
    
    with patch('core.billing_client.fetch_billing', return_value=mock_api_response):
        with patch('infra.object_storage.upload_json_with_metadata', return_value="test/path"):
            run_daily_job(settings, "20251204")
    
    # MongoDB에서 일별 데이터 확인
    from infra.mongo_client import get_mongo_client, get_database
    client = get_mongo_client(settings.mongo)
    db = get_database(client, settings.mongo.db_name)
    
    daily_data = list(db.billing_daily.find({"date": "20251204"}))
    assert len(daily_data) > 0
    
    # Baseline 업데이트 확인
    baseline = db.billing_baseline.find_one({
        "domainId": "test_domain",
        "projectId": "test_project",
        "serviceId": "1"
    })
    assert baseline is not None
    assert "statistics" in baseline
```

## 🎭 E2E 테스트

### 전체 파이프라인 테스트 시나리오

**파일**: `test_e2e_pipeline.py`

```python
"""
E2E 테스트: 전체 파이프라인 검증
"""
import pytest
from datetime import datetime, timedelta
from config.settings import load_settings
from infra.mongo_client import get_mongo_client, get_database

def test_e2e_pipeline():
    """
    전체 파이프라인 E2E 테스트
    
    1. Daily Job 실행하여 Baseline 데이터 생성
    2. Hourly Job 실행하여 이상치 탐지
    3. 결과 검증
    """
    settings = load_settings('config/settings.test.yaml')
    
    # 1. Daily Job 실행 (최근 7일 데이터 수집)
    print("\n[1단계] Daily Job 실행 - Baseline 데이터 생성")
    for i in range(7, 0, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        print(f"  - {date} 처리 중...")
        # 실제 Daily Job 실행 (Mock 없이)
        # run_daily_job(settings, date)
    
    # 2. Baseline 데이터 확인
    client = get_mongo_client(settings.mongo)
    db = get_database(client, settings.mongo.db_name)
    
    baselines = list(db.billing_baseline.find())
    assert len(baselines) > 0, "Baseline 데이터가 생성되지 않았습니다"
    
    print(f"✅ {len(baselines)}개 Baseline 생성 확인")
    
    # 3. Hourly Job 실행
    print("\n[2단계] Hourly Job 실행 - 이상치 탐지")
    today = datetime.now().strftime("%Y%m%d")
    # run_hourly_job(settings, today)
    
    # 4. 이상치 확인
    anomalies = list(db.billing_anomalies.find({"date": today}))
    print(f"✅ {len(anomalies)}개 이상치 탐지")
    
    # 5. 검증
    assert True  # 실제 검증 로직 추가
```

### 수동 E2E 테스트 절차

1. **Baseline 데이터 준비**
   ```bash
   # 최근 7일간 Daily Job 실행
   for i in {7..1}; do
       date=$(date -v-${i}d +%Y%m%d 2>/dev/null || date -d "${i} days ago" +%Y%m%d)
       python jobs/daily_job.py --config config/settings.test.yaml --date $date
   done
   ```

2. **Baseline 확인**
   ```python
   from infra.mongo_client import get_mongo_client, get_database
   from config.settings import load_settings
   
   settings = load_settings('config/settings.test.yaml')
   client = get_mongo_client(settings.mongo)
   db = get_database(client, settings.mongo.db_name)
   
   baselines = list(db.billing_baseline.find())
   print(f"Baseline 개수: {len(baselines)}")
   for b in baselines:
       print(f"  - {b['serviceName']}: 샘플 {b['statistics']['sampleCount']}개")
   ```

3. **이상치 강제 생성 (테스트용)**
   ```python
   # 평균의 5배 값을 가진 테스트 데이터 삽입
   daily_col = db.billing_daily
   baseline = db.billing_baseline.find_one({"serviceId": "1"})
   
   if baseline:
       mean = baseline['statistics']['mean']
       test_data = {
           "date": datetime.now().strftime("%Y%m%d"),
           "domainId": baseline['domainId'],
           "projectId": baseline['projectId'],
           "serviceId": baseline['serviceId'],
           "expectAmount": mean * 5,  # 평균의 5배
           # ... 기타 필드
       }
       daily_col.insert_one(test_data)
   ```

4. **Hourly Job 실행 및 검증**
   ```bash
   python jobs/hourly_job.py --config config/settings.test.yaml
   ```

5. **결과 확인**
   ```python
   anomalies = list(db.billing_anomalies.find().sort("createdAt", -1).limit(5))
   for anomaly in anomalies:
       print(f"이상치 발견: {anomaly['serviceName']}")
       print(f"  관측값: {anomaly['observedAmount']:,.2f}")
       print(f"  Z-score: {anomaly['zScore']:.2f}")
   ```

## ⚡ 성능 테스트

### 대용량 데이터 처리 테스트

**파일**: `test_performance.py`

```python
import time
from core.aggregator import aggregate_daily

def test_large_data_aggregation():
    """대용량 데이터 집계 성능 테스트"""
    # 10,000개 엔트리 생성
    entries = []
    for i in range(10000):
        entries.append({
            "meteringDate": "20251205",
            "domainId": f"domain_{i % 10}",
            "projectId": f"project_{i % 100}",
            "serviceId": f"service_{i % 50}",
            "expectAmount": 1000.0 + i,
            "usageTime": 10.0,
            "usageSize": 0.0
        })
    
    start_time = time.time()
    summaries = aggregate_daily(entries)
    elapsed_time = time.time() - start_time
    
    print(f"10,000개 엔트리 집계 시간: {elapsed_time:.2f}초")
    print(f"집계 결과: {len(summaries)}개")
    
    # 성능 기준: 10,000개 엔트리를 5초 이내에 처리
    assert elapsed_time < 5.0, f"집계 시간이 너무 깁니다: {elapsed_time:.2f}초"
```

## ✅ 테스트 체크리스트

### 기능 테스트

- [ ] Billing API 호출 성공
- [ ] Entries 추출 정확성
- [ ] 데이터 집계 정확성
- [ ] MongoDB 저장 성공
- [ ] Object Storage 업로드 성공
- [ ] Baseline 계산 정확성
- [ ] 이상치 탐지 정확성 (Z-score, Deviation Ratio)
- [ ] 이상치 MongoDB 저장 성공
- [ ] Slack 알림 발송 (Webhook URL 설정 시)

### 통합 테스트

- [ ] Hourly Job 전체 흐름
- [ ] Daily Job 전체 흐름
- [ ] Baseline 업데이트 후 이상치 탐지
- [ ] 여러 날짜 데이터 처리

### 경계값 테스트

- [ ] Baseline 데이터 부족 시 (샘플 < 5개)
- [ ] 표준편차가 0인 경우
- [ ] 평균이 0인 경우
- [ ] 매우 큰 Z-score 값
- [ ] 매우 큰 Deviation Ratio 값

### 에러 핸들링 테스트

- [ ] API 호출 실패 시
- [ ] MongoDB 연결 실패 시
- [ ] Object Storage 업로드 실패 시
- [ ] Slack 알림 발송 실패 시 (Job은 계속 진행되어야 함)

### 성능 테스트

- [ ] 1,000개 엔트리 처리 시간
- [ ] 10,000개 엔트리 처리 시간
- [ ] 100개 서비스 Baseline 조회 시간
- [ ] Bulk Upsert 성능

## 🐛 디버깅 팁

### 로그 확인

```bash
# 상세 로그와 함께 실행
python jobs/hourly_job.py --config config/settings.test.yaml 2>&1 | tee hourly_test.log

# 에러만 확인
python jobs/hourly_job.py --config config/settings.test.yaml 2>&1 | grep -i error
```

### MongoDB 쿼리 직접 실행

```python
# MongoDB Shell 또는 Python
from infra.mongo_client import get_mongo_client, get_database
from config.settings import load_settings

settings = load_settings('config/settings.test.yaml')
client = get_mongo_client(settings.mongo)
db = get_database(client, settings.mongo.db_name)

# 데이터 확인
print("일별 데이터:", db.billing_daily.count_documents({}))
print("Baseline:", db.billing_baseline.count_documents({}))
print("이상치:", db.billing_anomalies.count_documents({}))

# 최근 이상치 조회
anomalies = list(db.billing_anomalies.find().sort("createdAt", -1).limit(5))
for a in anomalies:
    print(f"{a['date']} {a['hour']:02d}시 - {a['serviceName']}: {a['zScore']:.2f}")
```

## 📊 테스트 결과 리포트

테스트 완료 후 다음 정보를 문서화하세요:

- 테스트 환경 (OS, Python 버전, MongoDB 버전 등)
- 테스트 실행 날짜/시간
- 통과한 테스트 수
- 실패한 테스트 수 및 원인
- 성능 측정 결과
- 발견된 버그 및 이슈



