"""
공통 로깅 모듈

이 모듈은 Billing Job에서 사용하는 공통 로거를 제공합니다.
특히 Kakao Cloud 모니터링 에이전트가 수집하는 `/var/log/syslog`로
이상치 로그를 보내기 위해 Syslog 핸들러를 구성합니다.
"""

import logging
from logging.handlers import SysLogHandler


LOGGER_NAME = "billing_alert"


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """
    공통 로거를 반환합니다.

    - Syslog 핸들러를 통해 /var/log/syslog 에 로그를 남기도록 시도합니다.
    - 개발 환경 등에서 /dev/log 가 없을 경우, 콘솔 출력만 동작합니다.
    """
    logger = logging.getLogger(name)

    # 이미 설정된 로거가 있으면 그대로 반환
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "[%(levelname)s] %(asctime)s %(name)s %(message)s"
    )

    # Syslog 핸들러 설정 (/dev/log는 대부분의 Linux 배포판에서 syslog 소켓)
    try:
        syslog_handler = SysLogHandler(address="/dev/log")
        syslog_handler.setFormatter(formatter)
        logger.addHandler(syslog_handler)
    except OSError:
        # 로컬 개발 환경(macOS 등)에서 /dev/log가 없을 수 있으므로 무시
        pass

    # 콘솔 출력용 핸들러도 함께 추가
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


