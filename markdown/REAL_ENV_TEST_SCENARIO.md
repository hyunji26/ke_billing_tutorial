## 실환경 테스트 시나리오 (2개 VM 구성)

이 문서는 `billing_tutorial`을 **2개 VM 구성(Job VM + MongoDB VM)** 으로 실환경에서 검증하는 방법을 정리한 가이드입니다.

- **VM1 (Job VM)**: `billing_tutorial` 코드가 올라가 있고, `hourly_job.py`, `daily_job.py` 를 Cron으로 실행
- **VM2 (MongoDB VM)**: MongoDB 인스턴스 (`billing` DB, `billing_daily` / `billing_baseline` / `billing_anomalies` 컬렉션)
- **전제**: `billing_baseline`에는 이미 11월 한 달치 데이터를 집계·통계 낸 값이 들어가 있는 상태

---

## 1. MongoDB VM 준비

- **MongoDB 포트 오픈**
  - Mongo VM에서 **27017 포트가 Job VM에서만 접근 가능**하도록 보안 그룹/방화벽을 설정합니다.

- **컬렉션 구조 확인 (선택)**
  - Mongo VM에서 `mongosh` 접속:

```javascript
use billing
db.billing_baseline.countDocuments()
db.billing_daily.countDocuments()
db.billing_anomalies.countDocuments()
```

- **확인 포인트**
  - `billing_baseline` 문서 개수가 예상대로 나오는지만 우선 확인해두면 충분합니다.

---

## 2. Job VM에 코드 배포 및 환경 구성

### 2.1 필수 패키지 설치

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

### 2.2 GitHub에서 프로젝트 클론

```bash
cd ~                         # 예: 홈 디렉토리에서 작업 (sudo 없이 가능)
git clone <YOUR_GITHUB_REPO_URL> billing_tutorial
cd ~/billing_tutorial        # 아래 내용의 모든 /opt/billing_tutorial 은 이 경로에 맞게 변경
```

### 2.3 가상환경 및 패키지 설치

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. `config/settings.yaml` 작성

Job VM에서:

```bash
cd ~/billing_tutorial
# config/settings.yaml 파일을 열어 실환경 값으로 수정
```

`config/settings.yaml`을 실환경에 맞게 수정합니다 (핵심 부분 예시):

```yaml
billingApi:
  credentialId: "REAL_BILLING_API_ID"
  credentialSecret: "REAL_BILLING_API_SECRET"

mongo:
  uri: "mongodb://<MONGO_VM_INTERNAL_IP>:27017/billing"
  dbName: "billing"

objectStorage:
  endpoint: "https://object-storage.kr-central-2.kakaocloud.com"
  bucket: "your-real-bucket"
  accessKey: "REAL_ACCESS_KEY"
  secretKey: "REAL_SECRET_KEY"
```

- **파일**
  - `config/settings.py`: **파이썬 코드**로, YAML을 읽어서 `Settings` 객체로 변환하는 로더 역할입니다.
  - `config/settings.yaml`: **환경별 설정값이 들어가는 데이터 파일**입니다. (ID/Secret, Mongo URI 등)
  - 이름이 비슷하지만 **하나는 코드(.py), 하나는 실제 설정 값(.yaml)** 이라 역할이 다릅니다.

- **포인트**
  - **`mongo.uri`**: Job VM에서 Mongo VM으로 접속 가능한 주소여야 합니다.
  - **Object Storage**: Daily Job에서 Raw JSON 업로드에 필요하므로 실제 버킷/키를 넣어야 합니다.

---

## 4. 수동 실행으로 1차 검증

### 4.1 Hourly Job 수동 실행

Job VM에서:

```bash
# 오늘 날짜로 실행 (Billing API에 오늘 데이터가 있어야 함)
python jobs/hourly_job.py --config config/settings.yaml

# 또는 특정 테스트 날짜로 실행
python jobs/hourly_job.py --config config/settings.yaml --date 20251110
```

- **정상일 때 기대되는 것**
  - 터미널(또는 로그 파일)에 다음 단계 로그가 순서대로 출력:
    - `[1/6] Billing API 호출 중...`
    - `[2/6] Entries 추출 중...`
    - `[3/6] 데이터 집계 중...`
    - `[4/6] MongoDB 연결 중...`
    - `[5/6] Baseline 조회 중...`
    - `[6/6] 이상치 탐지 중...`
    - 마지막에 `✅ Hourly Job 완료!`

- **MongoDB에서 확인 (Mongo VM 또는 Job VM에서 Python으로)**

```python
from config.settings import load_settings
from infra.mongo_client import get_mongo_client, get_database

settings = load_settings("config/settings.yaml")
client = get_mongo_client(settings.mongo)
db = get_database(client, settings.mongo.db_name)

print("anomalies:", db.billing_anomalies.count_documents({}))
print("daily:", db.billing_daily.count_documents({}))
```

- **주의**
  - 이상치가 실제로 탐지될지는 데이터에 따라 다릅니다.
  - 이 단계에서 중요한 것은 **에러 없이 실행되고, 컬렉션에 insert/upsert가 되는지**입니다.

### 4.2 Daily Job 수동 실행

```bash
cd /opt/billing_tutorial
source venv/bin/activate

# 특정 날짜(예: 2025-11-10)에 대해 실행
python jobs/daily_job.py --config config/settings.yaml --date 20251110
```

- **정상 기대**
  - 콘솔에 5단계 로그 (`[1/5]` ~ `[5/5]`) 가 순서대로 출력
  - MongoDB:
    - `billing_daily` 에 해당 날짜 데이터가 저장
    - `billing_baseline` 일부 서비스의 통계가 재계산(업데이트) 될 수 있음

---

## 5. Cron으로 자동 실행 설정 (+ 로그 파일)

이미 `scripts/setup_cron.sh` 가 준비되어 있으므로 Job VM에서 한 번만 실행하면 됩니다.

```bash
cd /opt/billing_tutorial
source venv/bin/activate

# Cron 항목 추가
./scripts/setup_cron.sh add
```

- **결과**
  - **Hourly Job**: 매 시간 10분에 자동 실행
  - **Daily Job**: 매일 00:10에 자동 실행
  - **로그 파일 위치**:
    - `logs/hourly_job.log`
    - `logs/daily_job.log`

- **Cron 설정 확인**

```bash
crontab -l | grep billing_tutorial
```

---

## 6. Hourly Job 단계별 로그 확인

- **파일 기반 로그 확인 (기본)**

```bash
cd /opt/billing_tutorial
tail -n 100 logs/hourly_job.log
tail -n 100 logs/daily_job.log
```

- **실행 단위로 볼 때 기대되는 패턴**
  - `🕐 Hourly Job 실행 - YYYYMMDD HH:00`
  - `[1/6] ...` ~ `[6/6] ...`
  - `✅ Hourly Job 완료!`

- **이상치 관련 Syslog 로그 (Alert Center 연동)**
  - 이상치가 발생하면 `core.logger` 를 통해 `/var/log/syslog` 에 다음 형식의 로그가 남습니다:

```text
[BILLING_ANOMALY] date=20251208 hour=10 domainId=... projectId=... serviceId=... ...
```

  - Job VM에서 직접 확인:

```bash
sudo tail -n 100 /var/log/syslog | grep BILLING_ANOMALY
```

  - Kakao Cloud Monitoring 에이전트가 `/var/log/syslog` 를 수집하도록 설정해두면,  
    Alert Center에서 `BILLING_ANOMALY` 키워드 기반 알림 정책을 만들 수 있습니다.

---

## 7. 기능별 검증 포인트 체크리스트

- **Billing API 호출 정상 여부**
  - `logs/hourly_job.log` 에서 `[1/6] Billing API 호출 중...` 이후 예외 없이  
    `✅ API 호출 성공` 이 나오는지 확인합니다.

- **집계 로직 정상 여부**
  - `[3/6] 데이터 집계 중...` 이후  
    `✅ N개 서비스별 집계 완료` 에서 **N 값이 0이 아닌지** 확인합니다.

- **MongoDB 연동**
  - `[4/6] MongoDB 연결 중...` → `✅ MongoDB 연결 성공` 이 출력되는지
  - 시간이 지나면서 `billing_daily`, `billing_anomalies` 문서 수가 증가하는지 확인합니다.

- **Baseline 조회**
  - `[5/6] Baseline 조회 중...` → `✅ X개 Baseline 조회 완료`
  - **X가 0이면**:
    - 이번에 들어온 데이터의 `(domainId, projectId, serviceId)` 조합과  
      `billing_baseline` 의 키가 맞는지 확인이 필요합니다.

- **이상치 탐지**
  - `[6/6] 이상치 탐지 중...` → `✅ Y개 이상치 발견`
  - **Y > 0** 이고, `/var/log/syslog` 에 `[BILLING_ANOMALY]` 로그가 찍히는지 확인합니다.

---

## 8. 정리

- **이미 `billing_baseline` 이 준비된 상태**라면:
  - Job VM에서 `config/settings.yaml` 만 실환경에 맞게 설정하고,
  - `hourly_job` / `daily_job` 을 각각 1~2번 수동 실행해본 뒤,
  - `scripts/setup_cron.sh add` 로 Cron을 걸어주면,
  - **2개 VM 구성만으로 튜토리얼 전체를 실제 환경에서 검증**할 수 있습니다.

- 이후에는 필요에 따라:
  - 특정 시간대에 **일부러 이상치가 나오도록 테스트 데이터/조건을 조정**하거나,
  - Alert Center 알림 규칙을 세밀하게 다듬어  
    운영에 가까운 시나리오를 추가로 검증할 수 있습니다.


