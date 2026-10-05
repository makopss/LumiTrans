"""한국어 제품과 글로벌 제품 라인을 구분한다.

Lite/Full(설치 용량)과 별개다. 실행 중에는 환경 변수 WISE_PRODUCT가
assets/edition.json 보다 우선한다.
"""
import json
import os
import sys

_VALID = ("kr", "global")


def _edition_json_candidates():
    paths = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            paths.append(os.path.join(meipass, "assets", "edition.json"))
        paths.append(os.path.join(os.path.dirname(sys.executable), "assets", "edition.json"))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths.append(os.path.join(root, "assets", "edition.json"))
    return paths


def _product_from_edition_file():
    for path in _edition_json_candidates():
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        product = str(data.get("product", "")).strip().lower()
        if product in _VALID:
            return product
    return "kr"


def get_product() -> str:
    """'kr' 또는 'global'."""
    env = os.environ.get("WISE_PRODUCT", "").strip().lower()
    if env in _VALID:
        return env
    return _product_from_edition_file()


def is_global() -> bool:
    return get_product() == "global"
