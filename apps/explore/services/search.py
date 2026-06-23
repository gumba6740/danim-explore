# from django.contrib.postgres.search import TrigramSimilarity
# from django.core.cache import cache
# from django.db.models import Q, F, Count, Max
#
# from apps.posts.models import Post
#
#
# SEARCH_TTL = 60*60*24
# PAGE_LIMIT = 10
#
# def _search_key(search):
#     norm = search.strip().lower()
#     return f"search:{norm}"
#
# def _search(search):
#     key = _search_key(search)
#     cached = cache.get(key)
#     if cached is not None:
#         return cached
#
#     # qs = (
#     #     Post.objects.annotate(
#     #         sim=TrigramSimilarity("content", search)*4
#     #         + TrigramSimilarity("title", search)*4,
#     #         reaction=F("like_count") + F("comment_count") + Count("bookmarks", distinct=True),
#     #     )
#     #     .filter(Q(sim__gte=1.0) | Q(user__nickname__icontains=search))
#     #     .order_by("-sim")
#     # )
#
#     # qs = (
#     #     Post.objects.annotate(
#     #         title_sim=TrigramSimilarity("title", search),
#     #         content_sim=TrigramSimilarity("content", search),
#     #         reaction=F("like_count") + F("comment_count") + Count("bookmarks", distinct=True),
#     #     )
#     #     .filter(
#     #         Q(title_sim__gte=0.24)
#     #         | Q(content_sim__gte=0.24)
#     #         | Q(user__nickname__icontains=search)
#     #     )
#     # )
#
#     qs = (
#         Post.objects.annotate(
#             content_sim=TrigramSimilarity("content", search),
#             reaction=F("like_count") + F("comment_count") + Count("bookmarks", distinct=True),
#         )
#         .filter(
#             Q(title__icontains=search)  # 제목 부분일치
#             | Q(content_sim__gte=0.25)  # 본문 관련도
#             | Q(content__icontains=f"#{search}")
#             | Q(user__nickname__icontains=search)
#         )
#     )
#     result = list(qs[:500])
#
#     cutted = sorted(result, key=lambda i: i.reaction, reverse=True)[:325]
#     cutted_ids = [p.id for p in cutted]
#
#     cache.set(key, cutted_ids, SEARCH_TTL)
#     return cutted_ids
#
#
# def search_feed(search, page):
#     if not search.strip():
#         return []
#
#     ids = _search(search)
#     start = page * PAGE_LIMIT
#     page_ids = ids[start:start + PAGE_LIMIT]
#     if not page_ids:
#         return []
#
#     posts = (
#         Post.objects
#         .select_related("user")
#         .prefetch_related("spots__location")
#         .filter(id__in=page_ids)
#     )
#     order = {pid: idx for idx, pid in enumerate(page_ids)}
#     return sorted(posts, key=lambda p: order[p.id])




""" 임베딩 버전 ============================================
def _search(search):
    key = _search_key(search)
    cached = cache.get(key)
    if cached is not None:
        return cached

    query_vec = embed_query(search)

    qs = (
        Post.objects.annotate(
            trigram=TrigramSimilarity("content", search)
            + TrigramSimilarity("title", search) * 3
            + Max(TrigramSimilarity("spots__location__place_name", search)),
            emb_sim=Value(1.0) - CosineDistance("embedding", query_vec),
            reaction=F("like_count") + F("comment_count") + Count("bookmarks", distinct=True),
        )
        .annotate(sim=F("trigram") + F("emb_sim") * Value(2.0))
        .filter(
            Q(trigram__gte=1.0)
            | Q(emb_sim__gte=0.7)
            | Q(user__nickname__icontains=search)
        )
        .order_by("-sim")
    )
    result = list(qs[:500])
    cutted = sorted(result, key=lambda i: i.reaction, reverse=True)[:325]
    cutted_ids = [p.id for p in cutted]

    cache.set(key, cutted_ids, SEARCH_TTL)
    return cutted_ids
"""


import re
from django.contrib.postgres.search import TrigramSimilarity
from django.core.cache import cache
from django.db.models import Q, F, Count, Case, When, Value, FloatField

from apps.posts.models import Post


SEARCH_TTL = 60 * 60 * 24
PAGE_LIMIT = 10
CONTENT_SIM_THRESHOLD = 0.25

# 단독 자모(ㄱ-ㅎ, ㅏ-ㅣ) 제거용 — "용ㅇ인" -> "용인"
_LONE_JAMO = re.compile(r"[\u3131-\u318E]")


def _clean(search):
    return _LONE_JAMO.sub("", search).strip()


def _search_key(tokens):
    norm = " ".join(sorted(t.lower() for t in tokens))
    return f"search:{norm}"


def _search(tokens):
    key = _search_key(tokens)
    cached = cache.get(key)
    if cached is not None:
        return cached

    flt = Q()
    title_score = Value(0.0, output_field=FloatField())
    hashtag_score = Value(0.0, output_field=FloatField())
    content_sim = Value(0.0, output_field=FloatField())

    for t in tokens:
        # 검색어에 맞는 후보
        flt |= (
            Q(title__icontains=t)
            | Q(content__icontains=f"#{t}")
            | Q(user__nickname__icontains=t)
            | Q(**{f"content_sim_{t}__gte": CONTENT_SIM_THRESHOLD})
        )

        # 후보를 정렬할 점수
        title_score = title_score + Case(
            When(title__icontains=t, then=Value(3.0)),
            default=Value(0.0), output_field=FloatField(),
        )
        hashtag_score = hashtag_score + Case(
            When(content__icontains=f"#{t}", then=Value(2.0)),
            default=Value(0.0), output_field=FloatField(),
        )
        content_sim = content_sim + TrigramSimilarity("content", t)

    trigram_annots = {
        f"content_sim_{t}": TrigramSimilarity("content", t) for t in tokens
    }

    qs = (
        Post.objects.annotate(**trigram_annots)
        .annotate(
            title_score=title_score,
            hashtag_score=hashtag_score,
            content_score=content_sim,
        )
        .annotate(
            score=F("title_score") + F("hashtag_score") + F("content_score"),
        )
        .filter(flt)
        .order_by("-score", "-id")
        .distinct()
    )

    result = list(qs[:500])
    cutted_ids = [p.id for p in result[:325]]

    cache.set(key, cutted_ids, SEARCH_TTL)
    return cutted_ids


def search_feed(search, page):
    cleaned = _clean(search)
    tokens = cleaned.split()

    # 한 글자 이하 단일 토큰은 검색 안 함 (너무 많이 잡힘)
    if not tokens or (len(tokens) == 1 and len(tokens[0]) < 2):
        return []

    ids = _search(tokens)
    start = page * PAGE_LIMIT
    page_ids = ids[start:start + PAGE_LIMIT]
    if not page_ids:
        return []

    posts = (
        Post.objects
        .select_related("user")
        .prefetch_related("spots__location")
        .filter(id__in=page_ids)
    )
    order = {pid: idx for idx, pid in enumerate(page_ids)}
    return sorted(posts, key=lambda p: order[p.id])