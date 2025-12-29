# Kakao Cloud Billing Alert Tutorial

Kakao Cloud Billing API를 활용한 비용 데이터 수집, 집계, 이상치 탐지 및 알림 파이프라인입니다.

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
