from ulid import ULID


def generate_ulid() -> str:
    """시간 기반 정렬 가능한 26자리 ID 생성 (UUID v4 대비 인덱스 성능 우위)"""
    return str(ULID())
