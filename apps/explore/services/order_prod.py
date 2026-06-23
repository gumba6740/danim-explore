import math
import random
from datetime import timedelta, datetime
from itertools import chain

from django.db.models import F
from django.utils import timezone

from apps.posts.models import Post

#
SIGMOID_C = 300  # 시그모이드 중심 — 감쇠 배율이 0.5 되는 나이(일)
SIGMOID_S = 4  # 시그모이드 가파름 — 클수록 위로 볼록 + 중간 급락
COLD_ALPHA = 2.0  # ALPHA 클수록 인기순에 가깝고, 0이면 완전 균등 랜덤

#
NEW_MAX_DAYS = 7   # now-7d  < created_at <= now
MAIN_MAX_DAYS = 30  # now-30d < created_at <= now-7d
SUB_MAX_DAYS = 90   # now-90d <= created_at <= now-30d

#
NEW_POOL = 120

MAIN_POOL = 100
MAIN_CUT = 50

SUB_POOL = 100
SUB_CUT = 30

#
NEW_SCORED_PERSONAL = 1.0
MAIN_PERSONAL       = 1.0
SUB_PERSONAL        = 1.0

PERSONALIZATION_BETA = 2.5


def _reaction(post):
    return math.log1p(post.like_count + post.comment_count)


def _age_days(post, now):
    return max(0.0, (now - post.created_at).total_seconds() / (60*60*24))


def _sigmoid_decay(age_days, center=SIGMOID_C, scale=SIGMOID_S):
    """
    S자 모양 감쇠 곡선.
    center: 절반으로 감소하는 시간. center가 12일이라면 12일만에 절반으로 감소.
    scale: 클수록 그래프 곡선의 볼록함 정도가 올라감.
    """
    return 1.0 / (1.0 + (age_days / center) ** scale)


def _rookie_score(post):
    """
    신규 구간의 인기글 추천용.
    한 게시글이 생성된지 7일까지가 사실상 신규글, 비인기글이 사람들에게 노출이 될 수 있는 마지노선.
    """
    return _reaction(post)


def _main_score(post, now):
    """
    신규와 올드 구간 사이의 인기글 추천용.
    오래된 글일수록 reaction 점수가 높기 때문에 시간감쇠로 균형을 맞춤.
    밸런스를 잡기 어려워 조회수는 점수에 반영하지 않음.
    """
    return _reaction(post) * _sigmoid_decay(_age_days(post, now))


def _sub_score(post, now):
    """
    올드 구간의 인기글 추천용.
    이미 시간이 충분히 지난 글을 추천하려는 목적이기에 시간감쇠는 없앰.
    로그를 씌운 조회수를 점수에 반영.
    """
    return _reaction(post) * math.log1p(post.view_count) * _sigmoid_decay(_age_days(post, now))


# 코드워드 개인화 ============================================================
def _post_embedding(post):
    """post 에 연결된 PostEmbedding 을 반환. 없으면 None.
    (select_related('vector') 로 미리 당겨오면 추가 쿼리 없음)"""
    try:
        return post.vector            # OneToOne related_name='vector'
    except Exception:
        return None


def _post_affinity(post, profile):
    """
    유저 codeword_counts 와 후보 글 codewords 의 코사인 유사도 [0, 1].
    두 희소 벡터(칸 기준)의 겹침. 가중치가 모두 음 아님 → 결과 0~1.

    글의 codebook_version 이 taste 의 버전과 다르면 코드워드 아이디가 서로
    다른 코드북을 가리키므로 코사인이 무의미 → 0(개인화 스킵)으로 빠진다.
    """
    taste_counts = profile.counts
    u_norm = profile.norm
    taste_version = profile.version

    if not taste_counts or u_norm == 0.0:
        return 0.0
    emb = _post_embedding(post)
    if emb is None:
        return 0.0
    # 버전 가드: 글 임베딩 버전과 taste 버전이 같을 때만 채점
    if taste_version is not None and emb.codebook_version != taste_version:
        return 0.0
    cws = emb.codewords or None
    if not cws:
        return 0.0
    dot = 0.0
    p_sq = 0.0
    for cw in cws:
        w = float(cw.get("weight", 0.0))
        p_sq += w * w
        uw = taste_counts.get(str(cw["codeword"]))
        if uw:
            dot += float(uw) * w
    if dot == 0.0 or p_sq == 0.0:
        return 0.0
    return dot / (u_norm * math.sqrt(p_sq))


def _affinity_boosted(base_score_fn, weighted_alpha, profile):
    """기본 스코어 함수에 코드워드 개인화 점수를 가미하는 고차 함수.
    affinity = exp(BETA * cos) 형태는 기존 덴스 벡터 방식과 동일."""

    def score_fn(post):
        base = base_score_fn(post)
        if profile.norm == 0.0:
            return base
        cos = _post_affinity(post, profile)
        if cos <= 0.0:
            return base
        affinity = math.exp(PERSONALIZATION_BETA * cos)
        # alpha 는 0 이상 1 이하
        return base * (affinity ** weighted_alpha)

    return score_fn


# 가중 랜덤 순열 ============================================================
def _weighted_order(posts, score_fn, *, seed, cold_alpha=COLD_ALPHA):
    """점수에 난수를 반영한 키로 posts를 정렬하는 함수"""
    key_p = []
    for p in posts:
        weight = (score_fn(p) + 1) ** cold_alpha
        # 시드와 posts가 같으면 항상 같은 피드가 나오도록. u는 0 이상 1 미만의 수
        u = random.Random(f"{seed}:{p.id}").random()
        key = u ** (1.0 / weight)
        key_p.append((key, p))
    # key가 큰 순으로 정렬. key는 점수에 난수를 반영한 정렬용 수.
    key_p.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in key_p]
# def _weighted_order(posts, score_fn, *, seed, cold_alpha=COLD_ALPHA):
#     scored = [(p, score_fn(p)) for p in posts]
#     mx = max((s for _, s in scored), default=1.0) or 1.0
#     key_p = []
#     for p, s in scored:
#         norm = (s / mx) ** 0.5            # 0~1 정규화 (sqrt로 약간 완화)
#         u = random.Random(f"{seed}:{p.id}").random()
#         key = cold_alpha * norm + (1 - cold_alpha) * u   # cold_alpha는 0~1
#         key_p.append((key, p))
#     key_p.sort(key=lambda t: t[0], reverse=True)
#     return [p for _, p in key_p]


def _random_pool(base_qs, pool_size, seed_key, *, personalize=False):
    """랜덤한 풀을 pool_size만큼 가져오는 함수.
    개인화 시 codewords 채점을 위해 PostEmbedding(vector)을 select_related 로 당겨온다."""
    cut = random.Random(seed_key).random()

    def _fetch(qs):
        if personalize:
            qs = qs.select_related("vector")
        return qs

    head = _fetch(base_qs.filter(random_score__gte=cut).order_by("random_score"))
    pool = list(head[:pool_size])

    # pool_size보다 모자라면 cut 미만에서 처음부터 채움
    if len(pool) < pool_size:
        tail = _fetch(base_qs.filter(random_score__lt=cut).order_by("random_score"))
        pool += list(tail[:pool_size - len(pool)])

    return pool


def new_order(now, seed, *, profile):
    """
    now-7d ~ now 간의 posts를 최대 NEW_POOL개 랜덤 추출해서
    루키순/랜덤순으로 각각 정렬 후, 번갈아 합침(중복 제거).
    """
    # hi = now
    # lo = now - timedelta(days=NEW_MAX_DAYS)
    lo1 = datetime(2026, 4, 24, 0, 0, 0)
    hi2 = datetime(2026, 4, 30, 23, 59, 59)
    lo = timezone.make_aware(lo1)
    hi = timezone.make_aware(hi2)

    personalize = profile.active

    base_qs = (
        Post.objects.select_related("user")
        .filter(created_at__gt=lo, created_at__lte=hi)
        .annotate(reaction=F("like_count") + F("comment_count"))
    )

    posts = _random_pool(
        base_qs, NEW_POOL, f"{seed}:new:cut",
        personalize=personalize,
    )

    # rookie 점수에 개인화 반영
    if personalize:
        scored_fn = _affinity_boosted(
            _rookie_score, profile.alpha * NEW_SCORED_PERSONAL, profile
        )
    else:
        scored_fn = _rookie_score
    scored = _weighted_order(posts, scored_fn, seed=f"{seed}:new:scored")

    # 점수 0.0이면 완전 랜덤
    shuffled = _weighted_order(posts, lambda p: 0.0,
                               seed=f"{seed}:new:rand", cold_alpha=0.0)

    merged, used = [], set()
    for p in chain.from_iterable(zip(scored, shuffled)):
        if p.id not in used:
            used.add(p.id)
            merged.append(p)
    return merged


def main_order(now, seed, *, profile):
    """now-30d ~ now-7d 간의 posts를 정렬하는 함수"""
    personalize = profile.active
    # hi = now - timedelta(days=NEW_MAX_DAYS)
    # lo = now - timedelta(days=MAIN_MAX_DAYS)
    lo1 = datetime(2026, 4, 1, 0, 0, 0)
    hi2 = datetime(2026, 4, 23, 23, 59, 59)
    lo = timezone.make_aware(lo1)
    hi = timezone.make_aware(hi2)
    base_qs = (
        Post.objects
        .select_related("user")
        .filter(created_at__gt=lo, created_at__lte=hi)
        .annotate(reaction=F("like_count") + F("comment_count"))
    )

    # reaction 순 대신 random_score 기준 랜덤 추출
    pool = _random_pool(
        base_qs, MAIN_POOL, f"{seed}:main:cut",
        personalize=personalize,
    )

    base_score_fn = lambda p: _main_score(p, now)
    score_fn = (
        _affinity_boosted(base_score_fn, profile.alpha * MAIN_PERSONAL, profile)
        if personalize else base_score_fn
    )
    return _weighted_order(pool, score_fn, seed=f"{seed}:main")[:MAIN_CUT]


def sub_order(now, seed, *, profile):
    """now-90d ~ now-30d 의 posts를 정렬하는 함수."""
    personalize = profile.active
    # hi = now - timedelta(days=MAIN_MAX_DAYS)
    # lo = now - timedelta(days=SUB_MAX_DAYS)
    lo1 = datetime(2026, 2, 1, 0, 0, 0)
    hi2 = datetime(2026, 3, 31, 23, 59, 59)
    lo = timezone.make_aware(lo1)
    hi = timezone.make_aware(hi2)
    base_qs = (
        Post.objects
        .select_related("user")
        .filter(created_at__gte=lo, created_at__lte=hi)
        .annotate(reaction=F("like_count") + F("comment_count"))
    )

    pool = _random_pool(
        base_qs, SUB_POOL, f"{seed}:sub:cut",
        personalize=personalize,
    )

    base_score_fn = lambda p: _sub_score(p, now)
    score_fn = (
        _affinity_boosted(base_score_fn, profile.alpha * SUB_PERSONAL, profile)
        if personalize else base_score_fn
    )
    return _weighted_order(pool, score_fn, seed=f"{seed}:sub")[:SUB_CUT]
