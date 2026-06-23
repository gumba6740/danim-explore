import math
import random
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone

from apps.explore.services.order_prod import main_order, sub_order, new_order
from apps.posts.models import Post
from apps.users.models import UserTaste

# N:5, M:4, S:1 — 아래 COUNT 상수와 개수가 일치해야 함(assert 로 강제)
SLOT_LAYOUT = ["N", "M", "N", "M", "N", "S", "N", "M", "N", "M"]

CACHE_TTL = 60 * 30

#
NEW_COUNT = 5
MAIN_COUNT = 4
SUB_COUNT = 1
PAGE_SIZE = NEW_COUNT + MAIN_COUNT + SUB_COUNT

assert SLOT_LAYOUT.count("N") == NEW_COUNT
assert SLOT_LAYOUT.count("M") == MAIN_COUNT
assert SLOT_LAYOUT.count("S") == SUB_COUNT

def _user_norm(taste_counts):
    """norm 계산"""
    if not taste_counts:
        return 0.0
    return math.sqrt(sum(float(v) * float(v) for v in taste_counts.values()))

@dataclass
class TasteProfile:
    counts: dict | None = None
    version: str | None = None
    alpha: float = 0.0
    norm: float = 0.0

    @classmethod
    def from_taste(cls, taste):
        if taste is None:
            return cls()
        counts = taste.codeword_counts or None
        return cls(
            counts=counts,
            version=taste.codebook_version,
            alpha=taste.alpha,
            norm=_user_norm(counts),   # ← 여기서 딱 한 번
        )

    @property
    def active(self) -> bool:
        return bool(self.counts) and self.alpha > 0

def get_explore_feed(viewer=None, *, page=0, seed=None, limit=PAGE_SIZE):
    """최종적으로 게시글 리스트를 반환하는 함수"""
    # 새로고침 등의 이유로 seed를 유저가 안 주면 seed 발급.
    # 클라가 문자열로 되돌려줄 수 있어 int 로 캐스팅(캐시 seed 비교 일관성).
    seed = random.randrange(1 << 30) if seed is None else int(seed)

    # taste_counts: 유저의 코드워드 취향 맵 {"36": 12.4, ...}. 후보 글 codewords 와 겹칠수록 추천
    # taste_version: 그 맵이 어느 코드북 버전 기준인지. 글 버전과 다르면 채점에서 스킵
    # alpha: 개인화 정도. 높을수록 취향이 많이 반영됨
    # taste_counts, taste_version, alpha = None, None, 0.0
    # if viewer is not None and viewer.is_authenticated:
    #     taste = UserTaste.objects.filter(user=viewer).first()
    #     if taste is not None:
    #         taste_counts = taste.codeword_counts or None
    #         taste_version = taste.codebook_version
    #         alpha = taste.alpha

    if viewer is not None and viewer.is_authenticated:
        profile = TasteProfile.from_taste(UserTaste.objects.filter(user=viewer.id).first())
    else:
        profile = TasteProfile()

    feed = _feed(
        page=page, seed=seed, limit=limit, viewer=viewer, profile=profile,
    )
    return feed, seed


def _feed(*, page, seed, limit, viewer=None, profile):
    """post id 목록을 페이지 수만큼 잘라서 DB에서 post를 불러오는 함수."""
    # 시(hour) 단위로 버킷팅 → 캐시가 페이지 사이에 evict 돼도 같은 시 안에선
    # 재빌드 결과가 동일해 페이지 경계 중복/누락 방지.
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    all_ids = _get_or_build_order(
        now, seed, viewer=viewer, profile=profile,
    )

    start = page * limit
    page_ids = all_ids[start:start + limit]
    if not page_ids:
        return []

    posts = Post.objects.select_related("user").filter(id__in=page_ids)
    order = {pid: idx for idx, pid in enumerate(page_ids)}
    return sorted(posts, key=lambda p: order[p.id])


def _get_or_build_order(now, seed, *, viewer=None, profile):
    """redis 에서 정렬된 id 리스트를 꺼내거나, 없으면 만들어 저장."""
    if viewer is not None and viewer.is_authenticated:
        uid = viewer.id
    else:
        # anon 은 전부 한 키를 공유하면 서로 덮어쓰며 thrash → seed 로 분리
        uid = f"anon:{seed}"
    key = _explore_list_key(uid)
    cached = cache.get(key)
    if cached is not None and cached["seed"] == seed:
        return cached["ids"]

    feed_ids = _build_full_order(
        now, seed, profile=profile,
    )
    cache.set(key, {"seed": seed, "ids": feed_ids}, CACHE_TTL)
    return feed_ids


def _explore_list_key(uid):
    return f"feed:{uid}"


def _build_full_order(now, seed, *, profile):
    orders = {
        "M": main_order(now, seed, profile=profile),
        "N": new_order(now, seed, profile=profile),
        "S": sub_order(now, seed, profile=profile),
    }
    used = set()
    feed_ids = []
    cursor = {"M": 0, "N": 0, "S": 0}

    while True:
        added = False
        for slot in SLOT_LAYOUT:
            bucket = orders[slot]
            i = cursor[slot]
            if i < len(bucket):
                cursor[slot] = i + 1
                post = bucket[i]
                if post.id not in used:
                    used.add(post.id)
                    feed_ids.append(post.id)
                    added = True
        if not added:
            break

    return feed_ids