from collections import defaultdict

from django.utils import timezone
import numpy as np
from apps.interactions.models import PostLike, PostClick, PostBookmark
from apps.comments.models import Comment
from apps.posts.models import PostEmbedding

PERSONALIZATION_BETA = 3.0   # 임베딩 부스트 세기 (클수록 취향 쏠림)
SIGNAL_FULL = 100


TASTE_WEIGHTS = {
    "like":    0.8,
    "comment": 0.8,
    "click":   0.2,
    "bookmark": 1.2,
}

def personalization_alpha(user):
    now = timezone.now()

    def decayed_count(qs):
        total = 0.0
        for created_at in qs.values_list("created_at", flat=True):
            age_days = (now - created_at).days
            total += _sigmoid_decay(age_days, center=90, scale=3)
        return total

    likes = decayed_count(PostLike.objects.filter(user=user))
    comments = decayed_count(Comment.objects.filter(user=user))
    clicks = decayed_count(PostClick.objects.filter(user=user))
    bookmarks = decayed_count(PostBookmark.objects.filter(user=user))
    strength = likes*0.8 + comments*0.8 + bookmarks*1 + clicks*0.2
    alpha = min(1.0, strength / SIGNAL_FULL)

    last_active = _last_active_at(user)
    if last_active is None:
        return 0.0
    idle_days = (now - last_active).days
    return alpha * _sigmoid_decay(idle_days, center=7, scale=5)


def _sigmoid_decay(age_days, center=7, scale=5):
    return 1.0 / (1.0 + (age_days / center)**scale)


def _last_active_at(user):
    """유저의 가장 최근 활동일이 언제인지 확인하는 함수"""
    times = []
    for model in (PostLike, Comment, PostClick):
        latest = (model.objects.filter(user=user)
                  .order_by("-created_at")
                  .values_list("created_at", flat=True)
                  .first())
        if latest is not None:
            times.append(latest)
    return max(times) if times else None


def build_codeword_counts(user, version="v1"):
    """
    유저의 상호작용을 코드워드 카운트(희소 맵)로 누적해서 반환.

        {"20": 1.83, "10": 0.95, ...}   # codeword(str) -> 누적 가중치

    누적값 = 상호작용종류가중치(TASTE_WEIGHTS) × 시간감쇠(_sigmoid_decay) × 게시글 codeword 가중치
    build_taste_vec 과 동일한 가중치/감쇠를 쓰되, 결과를 벡터로 평균내지 않고
    코드워드별 카운트로 쌓는다. raw 로 저장하고 정규화는 추천 점수 낼 때 수행.
    상호작용이 하나도 없으면 None (콜드 스타터).
    """
    now = timezone.now()

    # 1) (post_id, 상호작용가중치, created_at) 이벤트 모으기 (좋아요/댓글/클릭/북마크)
    events = []
    sources = (
        (PostLike, TASTE_WEIGHTS["like"]),
        (Comment, TASTE_WEIGHTS["comment"]),
        (PostClick, TASTE_WEIGHTS["click"]),
        (PostBookmark, TASTE_WEIGHTS["bookmark"]),
    )
    for model, base_w in sources:
        for row in model.objects.filter(user=user).values("post_id", "created_at"):
            events.append((row["post_id"], base_w, row["created_at"]))

    if not events:
        return None

    # 2) 상호작용한 게시글들의 codewords 를 한 번에 로드 (해당 코드북 버전만)
    post_ids = {e[0] for e in events}
    codewords_by_post = {
        str(pe.post_id): pe.codewords
        for pe in PostEmbedding.objects.filter(
            post_id__in=post_ids, codebook_version=version
        ).only("post_id", "codewords")
    }

    # 3) 누적: 상호작용가중치 × 시간감쇠 × codeword가중치
    counts = defaultdict(float)
    for post_id, base_w, created_at in events:
        cws = codewords_by_post.get(str(post_id))
        if not cws:  # 임베딩/codewords 아직 없는 글은 스킵
            continue
        age_days = (now - created_at).days
        w = base_w * _sigmoid_decay(age_days, center=60, scale=2)
        for cw in cws:
            counts[str(cw["codeword"])] += w * cw["weight"]

    if not counts:
        return None

    return {k: round(v, 6) for k, v in counts.items()}