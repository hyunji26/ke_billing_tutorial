#!/bin/bash
#
# Billing Tutorial Cron 설정 스크립트
# Hourly Job과 Daily Job을 자동 실행하도록 cron을 설정합니다.
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 스크립트 디렉토리 (이 스크립트가 있는 위치)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Python 경로 찾기
PYTHON3=$(which python3)
if [ -z "$PYTHON3" ]; then
    echo -e "${RED}❌ python3를 찾을 수 없습니다.${NC}"
    exit 1
fi

# Job 스크립트 경로
HOURLY_JOB="$PROJECT_ROOT/jobs/hourly_job.py"
DAILY_JOB="$PROJECT_ROOT/jobs/daily_job.py"
CONFIG_FILE="$PROJECT_ROOT/config/settings.yaml"

# 설정 파일 확인
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}⚠️  설정 파일이 없습니다: $CONFIG_FILE${NC}"
    echo -e "${YELLOW}   config/settings_example.yaml을 참고하여 설정 파일을 생성하세요.${NC}"
    exit 1
fi

# Job 스크립트 확인
if [ ! -f "$HOURLY_JOB" ]; then
    echo -e "${RED}❌ Hourly Job 파일을 찾을 수 없습니다: $HOURLY_JOB${NC}"
    exit 1
fi

if [ ! -f "$DAILY_JOB" ]; then
    echo -e "${RED}❌ Daily Job 파일을 찾을 수 없습니다: $DAILY_JOB${NC}"
    exit 1
fi

# 로그 디렉토리 생성
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# Cron 항목 생성
HOURLY_CRON="10 * * * * cd $PROJECT_ROOT && $PYTHON3 $HOURLY_JOB --config $CONFIG_FILE >> $LOG_DIR/hourly_job.log 2>&1"
DAILY_CRON="10 0 * * * cd $PROJECT_ROOT && $PYTHON3 $DAILY_JOB --config $CONFIG_FILE >> $LOG_DIR/daily_job.log 2>&1"

# 현재 cron 설정 확인
CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")

# 함수: cron 항목이 이미 존재하는지 확인
cron_exists() {
    local pattern="$1"
    echo "$CURRENT_CRON" | grep -qF "$pattern"
}

# 함수: cron 항목 추가
add_cron() {
    local cron_entry="$1"
    local job_name="$2"
    
    if cron_exists "$cron_entry"; then
        echo -e "${YELLOW}⚠️  $job_name cron 항목이 이미 존재합니다.${NC}"
    else
        # NOTE:
        # - set -e 환경에서 `crontab -l`은 "no crontab for user"일 때 exit 1을 반환합니다.
        # - 이 상태로 `(crontab -l; echo ...) | crontab -` 를 실행하면 subshell이 중간에 종료되어
        #   echo가 실행되지 않고, 결과적으로 빈 crontab이 설치될 수 있습니다.
        # - 따라서 `crontab -l` 실패를 무시하고 기존 항목이 없으면 빈 상태에서 추가되도록 합니다.
        (crontab -l 2>/dev/null || true; echo "$cron_entry") | crontab -
        echo -e "${GREEN}✅ $job_name cron 항목이 추가되었습니다.${NC}"
    fi
}

# 함수: cron 항목 제거
remove_cron() {
    local pattern="$1"
    local job_name="$2"
    
    if cron_exists "$pattern"; then
        crontab -l 2>/dev/null | grep -vF "$pattern" | crontab -
        echo -e "${GREEN}✅ $job_name cron 항목이 제거되었습니다.${NC}"
    else
        echo -e "${YELLOW}⚠️  $job_name cron 항목이 존재하지 않습니다.${NC}"
    fi
}

# 메인 메뉴
show_menu() {
    echo ""
    echo "=========================================="
    echo "  Billing Tutorial Cron 설정"
    echo "=========================================="
    echo ""
    echo "1) Cron 항목 추가 (Hourly + Daily)"
    echo "2) Cron 항목 제거 (Hourly + Daily)"
    echo "3) 현재 Cron 설정 확인"
    echo "4) 종료"
    echo ""
}

# 현재 cron 설정 표시
show_current_cron() {
    echo ""
    echo "현재 Cron 설정:"
    echo "----------------------------------------"
    crontab -l 2>/dev/null | grep -E "(hourly_job|daily_job)" || echo "설정된 항목이 없습니다."
    echo "----------------------------------------"
    echo ""
}

# 메인 로직
main() {
    if [ "$1" == "add" ]; then
        echo -e "${GREEN}📅 Cron 항목 추가 중...${NC}"
        add_cron "$HOURLY_CRON" "Hourly Job"
        add_cron "$DAILY_CRON" "Daily Job"
        echo ""
        echo -e "${GREEN}✅ 설정 완료!${NC}"
        echo ""
        echo "추가된 Cron 항목:"
        echo "  - Hourly Job: 매 시간 10분"
        echo "  - Daily Job: 매일 00:10"
        echo ""
        echo "로그 파일 위치:"
        echo "  - $LOG_DIR/hourly_job.log"
        echo "  - $LOG_DIR/daily_job.log"
        echo ""
        show_current_cron
    elif [ "$1" == "remove" ]; then
        echo -e "${YELLOW}🗑️  Cron 항목 제거 중...${NC}"
        remove_cron "$HOURLY_CRON" "Hourly Job"
        remove_cron "$DAILY_CRON" "Daily Job"
        echo ""
        echo -e "${GREEN}✅ 제거 완료!${NC}"
        echo ""
        show_current_cron
    elif [ "$1" == "show" ]; then
        show_current_cron
    else
        # 대화형 메뉴
        while true; do
            show_menu
            read -p "선택하세요 (1-4): " choice
            case $choice in
                1)
                    add_cron "$HOURLY_CRON" "Hourly Job"
                    add_cron "$DAILY_CRON" "Daily Job"
                    echo ""
                    echo -e "${GREEN}✅ 설정 완료!${NC}"
                    show_current_cron
                    ;;
                2)
                    remove_cron "$HOURLY_CRON" "Hourly Job"
                    remove_cron "$DAILY_CRON" "Daily Job"
                    echo ""
                    echo -e "${GREEN}✅ 제거 완료!${NC}"
                    show_current_cron
                    ;;
                3)
                    show_current_cron
                    ;;
                4)
                    echo "종료합니다."
                    exit 0
                    ;;
                *)
                    echo -e "${RED}❌ 잘못된 선택입니다.${NC}"
                    ;;
            esac
        done
    fi
}

# 스크립트 실행
main "$@"

