"""중복 실행 방지.

QLocalServer/QLocalSocket(윈도우: 네임드 파이프, macOS/Linux: 유닉스 소켓)를 이용한
OS 표준 단일 인스턴스 잠금이다. 파일 잠금 방식과 달리 프로세스가 비정상 종료돼도 OS가
핸들을 정리해주므로 "이전 실행의 잠금 파일이 남아 재실행도 막히는" 문제가 없다.

exe를 실행 중인 상태에서 빌드하면 파일이 잠겨 있어 덮어쓰기가 실패하는 문제(개발 중
반복적으로 겪음)와는 별개로, 사용자가 실수로 두 번 실행해 같은 화면이 중복으로 뜨는
것을 막기 위한 기능이다.
"""

from PySide6.QtNetwork import QLocalServer, QLocalSocket

_LOCK_KEY = "UTGW-GroupwareApp-SingleInstanceLock"


def acquire_single_instance_lock() -> QLocalServer | None:
    """이미 실행 중인 인스턴스가 있으면 None을 반환한다. 없으면 이 프로세스가 잠금을 쥔
    QLocalServer를 반환한다 — 호출한 쪽에서 앱이 끝날 때까지 참조를 들고 있어야 한다
    (가비지컬렉션되면 잠금이 풀린다)."""
    probe = QLocalSocket()
    probe.connectToServer(_LOCK_KEY)
    already_running = probe.waitForConnected(200)
    probe.disconnectFromServer()
    probe.close()
    if already_running:
        return None

    # 이전 실행이 비정상 종료해 소켓 핸들이 남아있는 경우 정리 후 이 프로세스가 잠금을 가진다.
    QLocalServer.removeServer(_LOCK_KEY)
    server = QLocalServer()
    server.listen(_LOCK_KEY)
    return server
