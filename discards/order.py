# import math
# import random
# from datetime import datetime
# from itertools import chain
#
# from django.db.models import F, Count
# from django.utils import timezone
#
# from apps.posts.models import Post
#
# from pgvector.django import CosineDistance
#
# #
# SIGMOID_C = 12  # 시그모이드 중심 — 감쇠 배율이 0.5 되는 나이(일)
# SIGMOID_S = 4  # 시그모이드 가파름 — 클수록 위로 볼록 + 중간 급락
# COLD_ALPHA = 0.5  # ALPHA 클수록 인기순에 가깝고, 0이면 완전 균등 랜덤
#
# #
# NEW_COUNT = 4
# MAIN_COUNT = 5
# SUB_COUNT = 1
# PAGE_SIZE = NEW_COUNT + MAIN_COUNT + SUB_COUNT
#
# #
# NEW_MAX_DAYS = 7  # now-7d < created_at <= now
# MAIN_MAX_DAYS = 30  # now-30d < created_at <= now-72h
# SUB_MAX_DAYS = 90  # now-90d <= created_at <= now-30d
#
# #
# NEW_POOL = 120
#
# MAIN_POOL = 300
# MAIN_CUT = 150
#
# SUB_POOL = 100
# SUB_CUT = 30
#
# #
# NEW_SCORED_PERSONAL = 1.0
# MAIN_PERSONAL       = 1.0    # 개인화 정도 강하게
# SUB_PERSONAL        = 1.0    # 강하게
#
# #
# SLOT_LAYOUT = ["M", "M", "N", "M", "N", "M", "S", "N", "M", "N"]
#
# CACHE_TTL = 60 * 30
#
# PERSONALIZATION_BETA = 5.0
#
#
# # todo: 북마크
# def _reaction(post):
#     return post.like_count + post.comment_count
#
#
# def _age_days(post, now):
#     return max(0.0, (now - post.created_at).total_seconds() / (60*60*24))
#
#
# def _sigmoid_decay(age_days, center=SIGMOID_C, scale=SIGMOID_S):
#     """
#     S자 모양 감쇠 곡선.
#     center: 절반으로 감소하는 시간. center가 12일이라면 12일만에 절반으로 감소.
#     scale: 클수록 그래프 곡선의 볼록함 정도가 올라감.
#     """
#     return 1.0 / (1.0 + (age_days / center) ** scale)
#
#
# def _rookie_score(post):
#     """
#     신규 구간의 인기글 추천용.
#     한 게시글이 생성된지 7일까지가 사실상 신규글, 비인기글이 사람들에게 노출이 될 수 있는 마지노선.
#     """
#     return _reaction(post)
#
#
# def _main_score(post, now):
#     """
#     신규와 올드 구간 사이의 인기글 추천용.
#     오래된 글일수록 reaction 점수가 높기 때문에 시간감쇠로 균형을 맞춤.
#     밸런스를 잡기 어려워 조회수는 점수에 반영하지 않음.
#     """
#     return _reaction(post) * _sigmoid_decay(_age_days(post, now))
#
#
# def _sub_score(post, now):
#     """
#     올드 구간의 인기글 추천용.
#     이미 시간이 충분히 지난 글을 추천하려는 목적이기에 시간감쇠는 없앰.
#     로그를 씌운 조회수를 점수에 반영.
#     """
#     return _reaction(post) * math.log1p(post.view_count) * _sigmoid_decay(_age_days(post, now))
#
#
# def _affinity_boosted(base_score_fn, alpha):
#     """_main_score() 등 기본 스코어 함수를 받아 개인화 점수를 가미하는 고차 함수"""
#
#     def score_fn(post):
#         base = base_score_fn(post)
#         distance = getattr(post, "distance", None)
#         if distance is None:
#             return base
#
#         # distance는 일치하면 0, 정반대면 2
#         # 가까울수록 점수가 크도록 하기 위해 distance를 코사인화한 이후 밑이 e인 거듭제곱
#         cos = 1.0 - distance
#         affinity = math.exp(PERSONALIZATION_BETA * cos)
#         # alpha는 0 이상 1 이하의 값
#         return base * (affinity ** alpha)
#
#     return score_fn
#
#
# # 가중 랜덤 순열 ============================================================
# def _weighted_order(posts, score_fn, *, seed, cold_alpha=COLD_ALPHA):
#     """점수에 난수를 반영할 키로 posts를 정렬하는 함수"""
#     key_p = []
#     for p in posts:
#         weight = (score_fn(p) + 1) ** cold_alpha
#         # 시드와 posts가 같으면 항상 같은 피드가 나오도록. u는 0 이상 1 미만의 수
#         u = random.Random(f"{seed}:{p.id}").random()
#         key = u ** (1.0 / weight)
#         key_p.append((key, p))
#     # key가 큰 순으로 정렬. key는 점수에 난수를 반영한 정렬용 수.
#     key_p.sort(key=lambda t: t[0], reverse=True)
#     return [p for _, p in key_p]
#
#
# def _random_pool(base_qs, pool_size, seed_key, *, taste_vec=None, personalize=False):
#     """랜덤한 풀을 pool_size만큼 가져오는 함수."""
#     cut = random.Random(seed_key).random()
#
#     def _fetch(qs):
#         if personalize:
#             qs = qs.annotate(distance=CosineDistance("vector__embedding", taste_vec))
#         return qs
#
#     head = _fetch(base_qs.filter(random_score__gte=cut).order_by("random_score"))
#     pool = list(head[:pool_size])
#
#     # pool_size보다 모자라면 cut 미만에서 처음부터 채움
#     if len(pool) < pool_size:
#         tail = _fetch(base_qs.filter(random_score__lt=cut).order_by("random_score"))
#         pool += list(tail[:pool_size - len(pool)])
#
#     return pool
#
#
# def new_order(now, seed, *, taste_vec=None, alpha=0.0):
#     """
#     0d~7d 간의 posts를 최대 NEW_POOL개 랜덤 추출해서
#     루키순/랜덤순으로 각각 정렬 후, 번갈아 합침(중복 제거).
#     """
#     lo1 = datetime(2026, 4, 24, 0, 0, 0)
#     hi2 = datetime(2026, 4, 30, 23, 59, 59)
#     lo = timezone.make_aware(lo1)
#     hi = timezone.make_aware(hi2)
#     personalize = taste_vec is not None and alpha > 0
#
#     base_qs = (
#         Post.objects.select_related("user")
#         .filter(created_at__gt=lo, created_at__lte=hi)
#         .annotate(reaction=F("like_count") + F("comment_count"))
#     )
#
#     posts = _random_pool(
#         base_qs, NEW_POOL, f"{seed}:new:cut",
#         taste_vec=taste_vec, personalize=personalize,
#     )
#
#     # rookie 점수에 개인화 반영
#     if personalize:
#         scored_fn = _affinity_boosted(_rookie_score, alpha * NEW_SCORED_PERSONAL)
#     else:
#         scored_fn = _rookie_score
#     scored = _weighted_order(posts, scored_fn, seed=f"{seed}:new:scored")
#
#     # 점수 0.0이면 완전 랜덤
#     shuffled = _weighted_order(posts, lambda p: 0.0,
#                                seed=f"{seed}:new:rand", cold_alpha=0.0)
#
#     merged, used = [], set()
#     for p in chain.from_iterable(zip(scored, shuffled)):
#         if p.id not in used:
#             used.add(p.id)
#             merged.append(p)
#     return merged
#
#
# def main_order(now, seed, *, taste_vec=None, alpha=0.0):
#     """7d~30d 간의 posts를 정렬하는 함수"""
#     personalize = taste_vec is not None and alpha > 0
#     lo1 = datetime(2026, 4, 1, 0, 0, 0)
#     hi2 = datetime(2026, 4, 23, 23, 59, 59)
#     lo = timezone.make_aware(lo1)
#     hi = timezone.make_aware(hi2)
#     base_qs = (
#         Post.objects
#         .select_related("user")
#         .filter(created_at__gt=lo, created_at__lte=hi)
#         .annotate(reaction=F("like_count") + F("comment_count"))
#     )
#
#     # reaction 순 대신 random_score 기준 랜덤 추출
#     pool = _random_pool(
#         base_qs, MAIN_POOL, f"{seed}:main:cut",
#         taste_vec=taste_vec, personalize=personalize,
#     )
#
#     base_score_fn = lambda p: _main_score(p, now)
#     score_fn = _affinity_boosted(base_score_fn, alpha) if personalize else base_score_fn
#     return _weighted_order(pool, score_fn, seed=f"{seed}:main")[:MAIN_CUT]
#
#
# def sub_order(now, seed, *, taste_vec=None, alpha=0.0):
#     """30d~90d의 posts를 정렬하는 함수."""
#     personalize = taste_vec is not None and alpha > 0
#     lo1 = datetime(2026, 2, 1, 0, 0, 0)
#     hi2 = datetime(2026, 3, 31, 23, 59, 59)
#     lo = timezone.make_aware(lo1)
#     hi = timezone.make_aware(hi2)
#     base_qs = (
#         Post.objects
#         .select_related("user")
#         .filter(created_at__gte=lo, created_at__lte=hi)
#         .annotate(reaction=F("like_count") + F("comment_count"))
#     )
#
#     pool = _random_pool(
#         base_qs, SUB_POOL, f"{seed}:sub:cut",
#         taste_vec=taste_vec, personalize=personalize,
#     )
#
#     base_score_fn = lambda p: _sub_score(p, now)
#     score_fn = _affinity_boosted(base_score_fn, alpha) if personalize else base_score_fn
#     return _weighted_order(pool, score_fn, seed=f"{seed}:sub")[:SUB_CUT]
