"""앱 이름과 사용자 데이터 폴더 경로를 한곳에서 관리한다.

이전 이름(WiseEinstein)으로 저장된 설정·로그·CUDA 가속 팩이 있으면
처음 접근할 때 새 이름(LumiTrans) 폴더로 옮겨 기존 사용자의 설정을 보존한다.
"""
import os
import shutil

APP_NAME = "LumiTrans"
GLOBAL_APP_NAME = "LumiTrans Global"
LEGACY_APP_NAMES = ("WiseEinstein",)

_migrated = set()


def app_data_name() -> str:
    """설정·로그 폴더 이름. 글로벌 제품은 한국어 제품과 폴더를 공유하지 않는다."""
    from src.product import is_global
    return GLOBAL_APP_NAME if is_global() else APP_NAME


def _migrate_legacy(base: str) -> None:
    """base/<옛 이름> 폴더가 있고 base/LumiTrans 가 없으면 이름을 바꾼다 (한 번만)."""
    if not base or base in _migrated:
        return
    _migrated.add(base)
    target = os.path.join(base, APP_NAME)
    if os.path.exists(target):
        return
    for legacy in LEGACY_APP_NAMES:
        source = os.path.join(base, legacy)
        if not os.path.isdir(source):
            continue
        try:
            os.rename(source, target)
            print(f"[경로] 이전 데이터 폴더를 옮겼습니다: {source} -> {target}")
        except OSError:
            # 다른 프로세스가 파일을 잡고 있는 등 이름 변경이 안 되면 복사로 대신한다.
            try:
                shutil.copytree(source, target)
                print(f"[경로] 이전 데이터 폴더를 복사했습니다: {source} -> {target}")
            except Exception as error:
                print(f"[경로] 이전 데이터 폴더 이전 실패 (새 폴더 사용): {error}")
        return


def _ensure(base: str) -> str:
    name = app_data_name()
    if name == APP_NAME:
        _migrate_legacy(base)
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    return path


def roaming_data_dir() -> str:
    """설정·로그 저장 폴더 (%APPDATA%\\LumiTrans)."""
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return _ensure(base)


def local_data_dir() -> str:
    """대용량 로컬 데이터 폴더 (%LOCALAPPDATA%\\LumiTrans, 예: CUDA 가속 팩)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return _ensure(base)
