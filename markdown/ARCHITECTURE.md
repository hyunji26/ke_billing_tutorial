# 카카오 클라우드 환경 아키텍처 설계

카카오 클라우드 환경에서 Billing Alert Tutorial을 운영하기 위한 최적의 아키텍처 설계 문서입니다.

## 📋 목차

- [아키텍처 개요](#아키텍처-개요)
- [인프라 구성](#인프라-구성)
- [네트워크 설계](#네트워크-설계)
- [보안 설계](#보안-설계)
- [고가용성 설계](#고가용성-설계)
- [모니터링 및 로깅](#모니터링-및-로깅)
- [비용 최적화](#비용-최적화)
- [배포 가이드](#배포-가이드)

## 🏗️ 아키텍처 개요

### 전체 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    Public Internet / VPN                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Load Balancer (선택사항)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VPC: billing-alert-vpc                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Public Subnet: billing-alert-public                      │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  VM: billing-job-vm-1 (2vCPU, 4GB RAM)            │  │  │
│  │  │  - Hourly Job (Cron)                                │  │  │
│  │  │  - Daily Job (Cron)                                 │  │  │
│  │  │  - Python 3.8+                                      │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  VM: billing-job-vm-2 (2vCPU, 4GB RAM) [HA]       │  │  │
│  │  │  - Standby 또는 Active-Active                      │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Private Subnet: billing-alert-private                   │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  MongoDB: Managed MongoDB (또는 VM)               │  │  │
│  │  │  - billing_daily 컬렉션                            │  │  │
│  │  │  - billing_baseline 컬렉션                          │  │  │
│  │  │  - billing_anomalies 컬렉션                         │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Kakao Cloud Services                                │
│  ┌──────────────────┐  ┌──────────────────┐                  │
│  │  Billing API     │  │  Object Storage   │                  │
│  │  (External)      │  │  - Raw JSON 저장  │                  │
│  └──────────────────┘  └──────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Monitoring & Alert                                  │
│  ┌──────────────────────────────┐  ┌──────────────────────────┐ │
│  │  Kakao Cloud Monitoring      │  │  Kakao Cloud Alert Center│ │
│  │  Agent (BCS 로그 수집)       │  │  - 로그 기반 알림 정책   │ │
│  │  - /var/log/syslog           │  │  - 이메일/워크 등 채널   │ │
│  └──────────────────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 💻 인프라 구성

### 1. VM 구성 (권장 사양)

#### 옵션 1: 단일 VM 구성 (소규모/테스트 환경)

```
VM 사양:
- 인스턴스 타입: Standard (2vCPU, 4GB RAM)
- 디스크: SSD 50GB
- OS: Ubuntu 22.04 LTS
- 네트워크: Public IP 또는 Private IP + NAT Gateway
- 비용: 약 월 50,000원 ~ 80,000원
```

**장점**:
- 비용 효율적
- 관리 간단
- 소규모 환경에 적합

**단점**:
- 단일 장애점 (SPOF)
- 확장성 제한

#### 옵션 2: 이중화 VM 구성 (프로덕션 환경)

```
VM 1 (Primary):
- 인스턴스 타입: Standard (2vCPU, 4GB RAM)
- 디스크: SSD 50GB
- 역할: Hourly Job + Daily Job 실행

VM 2 (Secondary):
- 인스턴스 타입: Standard (2vCPU, 4GB RAM)
- 디스크: SSD 50GB
- 역할: Standby 또는 Active-Active
- 비용: 약 월 100,000원 ~ 160,000원
```

**장점**:
- 고가용성
- 장애 복구 용이
- 부하 분산 가능

**단점**:
- 비용 증가
- 관리 복잡도 증가

#### 옵션 3: Kubernetes 구성 (대규모 환경)

```
Kubernetes Cluster:
- Master Node: 1개 (2vCPU, 4GB RAM)
- Worker Node: 2개 (각 2vCPU, 4GB RAM)
- CronJob으로 Hourly/Daily Job 실행
- 비용: 약 월 200,000원 ~ 300,000원
```

**장점**:
- 자동 스케일링
- 컨테이너 기반 배포
- 고가용성

**단점**:
- 초기 설정 복잡
- 운영 복잡도 높음

### 2. MongoDB 구성

#### 옵션 1: Managed MongoDB (권장)

```
서비스: Kakao Cloud Managed MongoDB
- 인스턴스 타입: Standard (2vCPU, 4GB RAM)
- 스토리지: SSD 100GB
- 백업: 자동 백업 활성화
- 비용: 약 월 100,000원 ~ 150,000원
```

**장점**:
- 자동 백업 및 복구
- 관리 부담 최소화
- 고가용성 옵션 제공

#### 옵션 2: VM에 MongoDB 설치

```
VM 사양:
- 인스턴스 타입: Standard (4vCPU, 8GB RAM)
- 디스크: SSD 200GB
- MongoDB: Community Edition
- 비용: 약 월 80,000원 ~ 120,000원
```

**장점**:
- 비용 절감 가능
- 완전한 제어권

**단점**:
- 백업/복구 직접 관리
- 운영 부담 증가

### 3. Object Storage 구성

```
서비스: Kakao Cloud Object Storage
- 버킷: billing-raw-data
- 스토리지 클래스: Standard
- 라이프사이클 정책: 90일 후 Archive, 365일 후 삭제
- 비용: 사용량 기반 (약 월 10,000원 ~ 50,000원)
```

## 🌐 네트워크 설계

### VPC 구성

```
VPC: billing-alert-vpc
- CIDR: 10.0.0.0/16

Subnet 1: billing-alert-public
- CIDR: 10.0.1.0/24
- 용도: Job 실행 VM
- Internet Gateway 연결

Subnet 2: billing-alert-private
- CIDR: 10.0.2.0/24
- 용도: MongoDB (선택사항)
- NAT Gateway 연결 (아웃바운드만)
```

### 보안 그룹 규칙

#### Job VM 보안 그룹

```
Inbound:
- SSH (22): 관리자 IP만 허용
- (Billing API, Monitoring/Alert Center는 아웃바운드만 필요)

Outbound:
- HTTPS (443): 모든 대상 (Billing API, Object Storage, Monitoring/Alert Center)
- MongoDB 포트 (27017): Private Subnet만 허용
```

#### MongoDB 보안 그룹

```
Inbound:
- MongoDB (27017): Job VM 보안 그룹만 허용

Outbound:
- 없음 (또는 필요한 경우만)
```

## 🔒 보안 설계

### 1. Credential 관리

#### 옵션 1: Secrets Manager 사용 (권장)

```
Kakao Cloud Secrets Manager:
- Billing API Credential 저장
- MongoDB Password 저장
- Object Storage Access Key 저장
- 자동 로테이션 설정
```

**구현 예시**:
```python
# config/secrets_manager.py
from kakao_cloud_secrets import get_secret

def load_secrets():
    return {
        "billing_api_id": get_secret("billing-api-credential-id"),
        "billing_api_secret": get_secret("billing-api-credential-secret"),
        "mongo_password": get_secret("mongo-password"),
        "object_storage_key": get_secret("object-storage-access-key")
    }
```

#### 옵션 2: 환경 변수 사용

```bash
# /etc/environment 또는 .env 파일
export BILLING_API_ID="..."
export BILLING_API_SECRET="..."
export MONGO_PASSWORD="..."
```

**주의**: 파일 권한 설정 필요 (`chmod 600`)

### 2. 네트워크 보안

- **Private Subnet 사용**: MongoDB는 Private Subnet에 배치
- **Security Group**: 최소 권한 원칙 적용
- **VPN 접근**: 관리자 접근은 VPN 통해서만

### 3. 데이터 암호화

- **전송 중 암호화**: TLS/SSL 사용
- **저장 암호화**: MongoDB 암호화, Object Storage 암호화

## 🔄 고가용성 설계

### 1. VM 이중화 전략

#### Active-Standby 방식

```
VM 1 (Active):
- 모든 Job 실행
- Health Check 활성화

VM 2 (Standby):
- 대기 상태
- VM 1 장애 시 자동 전환 (Cron 재설정 또는 자동화 스크립트)
```

#### Active-Active 방식

```
VM 1:
- Hourly Job 실행 (매 시간 10분)
- Daily Job 실행 (매일 00:10)

VM 2:
- Hourly Job 실행 (매 시간 15분) - 다른 시간에 실행
- Daily Job 실행 (매일 00:15) - 다른 시간에 실행
- 또는 VM 1 장애 시 백업 역할
```

**구현 방법**:
```bash
# VM 1의 Cron
10 * * * * /path/to/hourly_job.py
10 0 * * * /path/to/daily_job.py

# VM 2의 Cron (다른 시간에 실행)
15 * * * * /path/to/hourly_job.py
15 0 * * * /path/to/daily_job.py
```

### 2. MongoDB 고가용성

```
Replica Set 구성:
- Primary: 1개
- Secondary: 2개
- 자동 Failover
```

### 3. 모니터링 및 자동 복구

```
Health Check:
- Job 실행 상태 모니터링
- VM 상태 모니터링
- MongoDB 연결 상태 확인

자동 복구:
- Job 실패 시 재시도
- VM 장애 시 알림 발송
- 자동 스케일링 (Kubernetes 환경)
```

## 📊 모니터링 및 로깅

### 1. 로그 수집

#### 로그 저장 위치

```
/var/log/billing/        # 애플리케이션 전용 로그 (선택)
/var/log/syslog          # 시스템 및 Billing 이상치 로그 (Alert Center 연동용)
```

#### 로그 로테이션 설정

```bash
# /etc/logrotate.d/billing
/var/log/billing/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 billing billing
}
```

### 2. 모니터링 지표

#### 시스템 지표

- CPU 사용률
- 메모리 사용률
- 디스크 사용률
- 네트워크 트래픽

#### 애플리케이션 지표

- Job 실행 성공/실패 횟수
- Job 실행 시간
- 이상치 탐지 횟수
- MongoDB 쿼리 성능
- API 호출 성공률

#### 알림 설정 (예시)

```
Critical:
- Job 연속 3회 실패
- MongoDB 연결 실패
- 디스크 사용률 90% 초과
 - Billing 이상치 로그(BILLING_ANOMALY) 감지

Warning:
- Job 실행 시간 5분 초과
- 이상치 탐지 횟수 급증 (로그 기반 모니터링)
- API 호출 지연
```

### 3. 대시보드 구성

```
Grafana 또는 Cloud Monitoring:
- Job 실행 상태 대시보드
- 이상치 탐지 통계
- 시스템 리소스 사용률
- 비용 추이 그래프
```

## 💰 비용 최적화

### 월 예상 비용 (프로덕션 환경)

```
VM (이중화):          100,000원 ~ 160,000원
MongoDB (Managed):   100,000원 ~ 150,000원
Object Storage:       10,000원 ~  50,000원
네트워크:             10,000원 ~  30,000원
─────────────────────────────────────────
총계:                220,000원 ~ 390,000원
```

### 비용 절감 방법

1. **VM 스펙 조정**: 초기에는 작은 스펙으로 시작, 필요 시 스케일 업
2. **스토리지 최적화**: Object Storage 라이프사이클 정책 활용
3. **예약 인스턴스**: 장기 사용 시 예약 인스턴스 할인 활용
4. **모니터링**: 사용하지 않는 리소스 제거

## 🚀 배포 가이드

### 1. VM 생성 및 설정

```bash
# 1. VM 생성 (Kakao Cloud Console 또는 CLI)
# 2. SSH 접속
ssh -i ~/.ssh/billing_key.pem ubuntu@<VM_IP>

# 3. 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 4. Python 설치
sudo apt install python3 python3-pip python3-venv -y

# 5. 프로젝트 클론
git clone <repository_url> /opt/billing_tutorial
cd /opt/billing_tutorial

# 6. 가상환경 생성 및 패키지 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 7. 설정 파일 생성
cp config/settings_example.yaml config/settings.yaml
# settings.yaml 편집 (Secrets Manager 또는 환경 변수 사용)

# 8. Cron 설정
./scripts/setup_cron.sh add

# 9. 로그 디렉토리 생성
sudo mkdir -p /var/log/billing
sudo chown $USER:$USER /var/log/billing
```

### 2. MongoDB 설정

```bash
# Managed MongoDB 사용 시
# 1. Kakao Cloud Console에서 Managed MongoDB 생성
# 2. Connection String 복사
# 3. settings.yaml에 MongoDB URI 입력

# 또는 VM에 직접 설치
sudo apt install mongodb -y
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

### 3. Object Storage 설정

```bash
# 1. Kakao Cloud Console에서 Object Storage 버킷 생성
# 2. Access Key 생성
# 3. settings.yaml에 정보 입력
```

### 4. 테스트 실행

```bash
# 1. Daily Job 테스트
python jobs/daily_job.py --config config/settings.yaml --date $(date -d "yesterday" +%Y%m%d)

# 2. Hourly Job 테스트
python jobs/hourly_job.py --config config/settings.yaml

# 3. 이상치 로그 및 Alert Center 연동 확인
sudo tail -f /var/log/syslog | grep BILLING_ANOMALY
```

### 5. 모니터링 설정

```bash
# 1. Health Check 스크립트 생성
cat > /opt/billing_tutorial/scripts/health_check.sh << 'EOF'
#!/bin/bash
# Job 실행 상태 확인
# MongoDB 연결 확인
# 디스크 사용률 확인
EOF

chmod +x /opt/billing_tutorial/scripts/health_check.sh

# 2. Cron에 Health Check 추가
crontab -e
# 매 5분마다 실행
*/5 * * * * /opt/billing_tutorial/scripts/health_check.sh
```

## 📝 체크리스트

### 배포 전 확인사항

- [ ] VM 생성 및 네트워크 설정 완료
- [ ] 보안 그룹 규칙 설정 완료
- [ ] MongoDB 생성 및 연결 테스트 완료
- [ ] Object Storage 버킷 생성 및 접근 테스트 완료
- [ ] Billing API Credential 확인 완료
- [ ] 모니터링 에이전트(Kakao Cloud) 설치 및 `/var/log/syslog` 수집 설정
- [ ] Alert Center 로그 기반 알림 정책(BILLING_ANOMALY 키워드) 생성
- [ ] 설정 파일 (`config/settings.yaml`) 작성 완료
- [ ] 패키지 설치 완료
- [ ] Cron 설정 완료
- [ ] 로그 디렉토리 생성 완료

### 배포 후 확인사항

- [ ] Daily Job 정상 실행 확인
- [ ] Hourly Job 정상 실행 확인
- [ ] MongoDB 데이터 저장 확인
- [ ] Object Storage 업로드 확인
- [ ] 이상치 탐지 동작 확인
- [ ] Slack 알림 발송 확인 (설정된 경우)
- [ ] 로그 수집 정상 동작 확인
- [ ] 모니터링 설정 완료

## 🔍 FAQ

### Q1: VM을 몇 개 띄워야 하나요?

**A**: 환경 규모에 따라 다릅니다.
- **소규모/테스트**: 1개 VM (2vCPU, 4GB RAM)
- **프로덕션**: 2개 VM (이중화, 각 2vCPU, 4GB RAM)
- **대규모**: Kubernetes Cluster (3개 이상 노드)

### Q2: MongoDB는 Managed를 써야 하나요?

**A**: 권장합니다. 자동 백업, 고가용성, 관리 부담 감소 등의 이점이 있습니다. 비용이 부담되면 VM에 직접 설치할 수도 있습니다.

### Q3: Slack Webhook URL이 없으면 어떻게 되나요?

**A**: Slack Webhook URL이 없어도 이상치 탐지는 정상적으로 작동합니다. 다만 Slack 알림만 발송되지 않고, 이상치는 MongoDB에 저장되므로 나중에 확인할 수 있습니다.

### Q4: 비용을 더 절감할 수 있나요?

**A**: 
- VM 스펙을 낮춤 (1vCPU, 2GB RAM으로 시작)
- Object Storage 라이프사이클 정책 활용
- 예약 인스턴스 사용
- 사용하지 않는 리소스 제거

### Q5: 고가용성을 어떻게 보장하나요?

**A**:
- VM 이중화 (Active-Standby 또는 Active-Active)
- MongoDB Replica Set
- Health Check 및 자동 복구 스크립트
- 모니터링 및 알림 설정




