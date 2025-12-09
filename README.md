# Kakao Cloud Billing Alert Tutorial

Kakao Cloud Billing API를 활용한 비용 데이터 수집, 집계, 이상치 탐지 및 알림 파이프라인입니다.

## 📋 목차

- [개요](#개요)
- [시스템 아키텍처](#시스템-아키텍처)
- [주요 기능](#주요-기능)
- [설치 및 설정](#설치-및-설정)
- [사용 방법](#사용-방법)
- [데이터 흐름](#데이터-흐름)
- [Slack 알림 설정](#slack-알림-설정)
- [트러블슈팅](#트러블슈팅)

## 🎯 개요

이 튜토리얼은 Kakao Cloud Billing API를 통해 비용 데이터를 수집하고, 통계적 방법(Z-score, Deviation Ratio)을 사용하여 이상치를 탐지하여 실시간으로 알림을 발송하는 자동화 파이프라인을 제공합니다.

### 주요 특징

- **실시간 이상치 탐지**: 매 시간마다 비용 데이터를 분석하여 이상치를 탐지
- **통계 기반 탐지**: Baseline 통계(평균, 표준편차)를 기반으로 한 과학적 이상치 탐지
- **자동화된 파이프라인**: Cron을 통한 자동 실행
- **데이터 보관**: MongoDB에 집계 데이터, Object Storage에 Raw 데이터 저장
- **알림 연동**: Slack Webhook을 통한 실시간 알림

## 🏗️ 시스템 아키텍처

### 전체 파이프라인 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Kakao Cloud Billing API                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Hourly Job (매 시간)                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 1. API 호출 (당일 데이터)                              │  │
│  │ 2. 데이터 집계 (메모리)                                │  │
│  │ 3. Baseline 조회 (MongoDB)                             │  │
│  │ 4. 이상치 탐지 (Z-score, Deviation Ratio)              │  │
│  │ 5. 이상치 저장 (MongoDB)                                │  │
│  │ 6. Slack 알림 발송 (설정된 경우)                        │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Daily Job (매일 1회)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 1. API 호출 (어제 데이터)                              │  │
│  │ 2. Raw 데이터 저장 (Object Storage)                    │  │
│  │ 3. 일별 집계 데이터 저장 (MongoDB)                      │  │
│  │ 4. Baseline 업데이트 (전체 데이터 기준 재계산)           │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      데이터 저장소                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   MongoDB     │  │   Object     │  │   Slack      │     │
│  │               │  │   Storage    │  │   (알림)      │     │
│  │ - billing_   │  │              │  │              │     │
│  │   daily       │  │ - Raw JSON   │  │ - 이상치     │     │
│  │ - billing_    │  │   (일별)     │  │   알림       │     │
│  │   baseline    │  │              │  │              │     │
│  │ - billing_    │  │              │  │              │     │
│  │   anomalies   │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 데이터 저장 구조

#### MongoDB 컬렉션

1. **`billing_daily`**: 일별 집계 데이터
   - 날짜별, 도메인별, 프로젝트별, 서비스별 집계
   - `expectAmount`, `usageTime`, `usageSize` 등

2. **`billing_baseline`**: Baseline 통계
   - 각 서비스별 통계값 (mean, std, min, max, p50, p95)
   - 이상치 탐지의 기준이 되는 데이터

3. **`billing_anomalies`**: 이상치 기록
   - 탐지된 이상치의 상세 정보
   - Z-score, Deviation Ratio, 관측값 등

#### Object Storage

- **경로 구조**: `raw/year=YYYY/month=MM/day=DD/billing_YYYYMMDD.json`
- **용도**: Raw 데이터 장기 보관, 재처리, 감사(Audit)

## 🚀 주요 기능

### 1. Hourly Job (매 시간 실행)

- **실행 주기**: 매 시간 10분 (Cron 설정)
- **기능**:
  - 당일 Billing API 데이터 수집
  - 실시간 집계 및 Baseline 비교
  - 이상치 탐지 (Z-score ≥ 3.0 또는 Deviation Ratio ≥ 2.0)
  - 이상치 MongoDB 저장 및 Slack 알림

### 2. Daily Job (매일 실행)

- **실행 주기**: 매일 00:10 (Cron 설정)
- **기능**:
  - 어제 Billing API 데이터 수집
  - Raw 데이터를 Object Storage에 저장
  - 일별 집계 데이터를 MongoDB에 저장
  - Baseline 통계 재계산 (전체 데이터 기준)

### 3. 이상치 탐지 알고리즘

- **Z-Score**: `(관측값 - 평균) / 표준편차`
  - 임계값: 3.0 (3시그마 규칙)
- **Deviation Ratio**: `관측값 / 평균`
  - 임계값: 2.0 (평균의 2배 이상)
- **조건**: Z-score 또는 Deviation Ratio 중 하나라도 임계값 초과 시 이상치로 판단

## 📦 설치 및 설정

### 1. 필수 요구사항

- Python 3.8 이상
- MongoDB (로컬 또는 클라우드)
- Kakao Cloud Object Storage (또는 S3 호환 스토리지)
- Kakao Cloud Billing API Credential

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 설정 파일 생성

```bash
cp config/settings_example.yaml config/settings.yaml
```

### 4. 설정 파일 작성

`config/settings.yaml` 파일을 열어 다음 정보를 입력합니다:

```yaml
billingApi:
  credentialId: "YOUR_BILLING_API_ID"
  credentialSecret: "YOUR_BILLING_API_SECRET"

mongo:
  uri: "mongodb://user:password@host:27017/billing"
  dbName: "billing"

objectStorage:
  endpoint: "https://object-storage.kakaocloud.com"
  bucket: "your-billing-raw-bucket"
  accessKey: "YOUR_ACCESS_KEY"
  secretKey: "YOUR_SECRET_KEY"

alert:
  slackWebhookUrl: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"  # 선택사항
```

**중요**: `slackWebhookUrl`이 비어있거나 설정되지 않으면, 이상치 탐지는 정상적으로 수행되지만 Slack 알림은 발송되지 않습니다. MongoDB에는 이상치가 저장되므로 나중에 확인할 수 있습니다.

## 🚀 사용 방법

### 수동 실행

#### Hourly Job 실행

```bash
# 오늘 날짜로 실행
python jobs/hourly_job.py --config config/settings.yaml

# 특정 날짜로 실행
python jobs/hourly_job.py --config config/settings.yaml --date 20251205
```

#### Daily Job 실행

```bash
# 어제 날짜로 실행 (기본값)
python jobs/daily_job.py --config config/settings.yaml

# 특정 날짜로 실행
python jobs/daily_job.py --config config/settings.yaml --date 20251205

# 오늘 날짜로 실행
python jobs/daily_job.py --config config/settings.yaml --today
```

### 자동 실행 (Cron 설정)

```bash
# Cron 설정 스크립트 실행
./scripts/setup_cron.sh

# 또는 직접 명령어로
./scripts/setup_cron.sh add    # Cron 항목 추가
./scripts/setup_cron.sh remove # Cron 항목 제거
./scripts/setup_cron.sh show   # 현재 설정 확인
```

## 📊 데이터 흐름

### Hourly Job 데이터 흐름

```
1. Billing API 호출
   ↓
2. Entries 추출 (extract_entries)
   ↓
3. 일별 집계 (aggregate_daily)
   ↓
4. Baseline 조회 (MongoDB)
   ↓
5. 이상치 탐지 (detect_anomalies)
   ├─ Z-score 계산
   ├─ Deviation Ratio 계산
   └─ 임계값 비교
   ↓
6. 이상치 처리
   ├─ MongoDB 저장 (billing_anomalies)
   └─ Slack 알림 (설정된 경우)
```

### Daily Job 데이터 흐름

```
1. Billing API 호출
   ↓
2. Object Storage 저장 (Raw JSON)
   ↓
3. Entries 추출 및 집계
   ↓
4. MongoDB 저장 (billing_daily)
   ↓
5. Baseline 재계산
   ├─ billing_daily에서 전체 데이터 조회
   ├─ 통계값 계산 (mean, std, p50, p95 등)
   └─ billing_baseline 업데이트
```

## 🔔 Slack 알림 설정

### Slack Webhook URL 생성

1. Slack 워크스페이스에 접속
2. [Apps] → [Incoming Webhooks] 검색
3. Webhook URL 생성
4. 생성된 URL을 `config/settings.yaml`의 `slackWebhookUrl`에 입력

### 알림 메시지 예시

```
🚨 Billing Anomaly Detected

Date/Time: 20251205 14:00
Domain: kakaoicloud-r (e8c5d648...)
Project: set-api-test (9e8654f9...)
Service: Virtual Machine (1)

Observed Amount: 50,000.00
Baseline Mean: 10,000.00
Z-Score: 20.00
Deviation Ratio: 5.00x

Threshold: Z-Score >= 3.0 or Ratio >= 2.0x
```

### Slack Webhook URL이 없는 경우

**질문**: Slack Webhook URL이 없으면 이상치 탐지는 안 되나요?

**답변**: 아니요. Slack Webhook URL이 없어도 이상치 탐지는 정상적으로 수행됩니다.

- ✅ **이상치 탐지**: 정상 작동
- ✅ **MongoDB 저장**: 정상 작동 (`billing_anomalies` 컬렉션에 저장)
- ❌ **Slack 알림**: 발송되지 않음

코드에서 확인:

```python
# jobs/hourly_job.py 153줄
if settings.alert.slack_webhook_url:
    send_slack_alert(anomaly, settings.alert.slack_webhook_url)
```

`slack_webhook_url`이 설정되어 있지 않으면 알림만 발송되지 않고, 이상치 탐지와 저장은 정상적으로 수행됩니다. 나중에 MongoDB에서 이상치를 조회할 수 있습니다.

## 🔍 트러블슈팅

### 1. 설정 파일 오류

**문제**: `FileNotFoundError: config/settings.yaml`

**해결**: `config/settings_example.yaml`을 복사하여 `config/settings.yaml`을 생성하고 필요한 정보를 입력하세요.

### 2. MongoDB 연결 실패

**문제**: `pymongo.errors.ServerSelectionTimeoutError`

**해결**: 
- MongoDB URI가 올바른지 확인
- 네트워크 연결 확인
- MongoDB 서버가 실행 중인지 확인

### 3. Object Storage 업로드 실패

**문제**: `RuntimeError: Object Storage 업로드 실패`

**해결**:
- Object Storage endpoint와 credentials 확인
- 버킷이 존재하는지 확인
- 네트워크 연결 확인

### 4. Billing API 호출 실패

**문제**: `requests.exceptions.HTTPError: 401 Unauthorized`

**해결**:
- `credentialId`와 `credentialSecret`이 올바른지 확인
- API 권한 확인

### 5. 이상치가 탐지되지 않음

**문제**: Baseline 데이터가 부족하여 이상치가 탐지되지 않음

**해결**:
- Daily Job을 여러 번 실행하여 충분한 데이터 수집
- Baseline은 최소 5개 이상의 샘플이 필요합니다 (`anomaly_detector.py` 102줄 참고)

### 6. Slack 알림이 발송되지 않음

**문제**: 이상치는 탐지되지만 Slack 알림이 오지 않음

**해결**:
- `config/settings.yaml`의 `slackWebhookUrl`이 올바르게 설정되었는지 확인
- Webhook URL이 유효한지 확인
- 네트워크 방화벽 설정 확인

## 📁 프로젝트 구조

```
billing_tutorial/
├── config/
│   ├── settings.py              # 설정 로더
│   └── settings_example.yaml     # 설정 파일 예시
├── core/
│   ├── billing_client.py        # Billing API 클라이언트
│   ├── aggregator.py            # 데이터 집계 로직
│   ├── baseline.py              # Baseline 계산/조회
│   ├── anomaly_detector.py      # 이상치 탐지
│   └── notifier.py              # 알림 발송
├── infra/
│   ├── mongo_client.py          # MongoDB 연동
│   └── object_storage.py        # Object Storage 연동
├── jobs/
│   ├── hourly_job.py            # Hourly Job
│   └── daily_job.py             # Daily Job
├── scripts/
│   └── setup_cron.sh            # Cron 설정 스크립트
├── requirements.txt
└── README.md
```

## 📚 추가 문서

- [테스트 방법](./TESTING.md)
- [클라우드 아키텍처 설계](./ARCHITECTURE.md)

## 📝 라이선스

이 프로젝트는 튜토리얼 목적으로 제공됩니다.

