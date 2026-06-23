# import json
# import random
# from datetime import datetime
#
# from django.core.cache import cache
# from django.utils import timezone
#
# from apps.explore.services.order import main_order, sub_order, new_order
# from apps.posts.models import Post
# from apps.users.models import UserTaste
#
# SLOT_LAYOUT = ["M", "N", "M", "N", "M", "N", "S", "N", "M", "N"]
#
# CACHE_TTL = 60 * 30
#
# PERSONALIZATION_BETA = 1.0
# #
# NEW_COUNT = 5
# MAIN_COUNT = 4
# SUB_COUNT = 1
# PAGE_SIZE = NEW_COUNT + MAIN_COUNT + SUB_COUNT
#
#
# def get_explore_feed(viewer=None, *, page=0, seed=None, limit=PAGE_SIZE):
#     """최종적으로 게시글 리스트를 반환하는 함수"""
#     # 새로고침 등의 이유로 seed를 유저가 안 주면 seed 발급
#     if seed is None:
#         seed = random.randrange(1 << 30)
#
#     # taste_vec: 유저의 취향 벡터. 이와 유사한 벡터를 가진 게시글을 추천
#     # alpha: 개인화 정도. 높을수록 취향벡터가 많이 반영됨
#     taste_vec, alpha = None, 0.0
#     if viewer is not None and viewer.is_authenticated:
#         taste = UserTaste.objects.filter(user=viewer).first()
#         if taste is not None:
#             taste_vec = taste.vector
#             alpha = taste.alpha
#
#     feed = _feed(
#         page=page, seed=seed, limit=limit,
#         viewer=viewer, taste_vec=taste_vec, alpha=alpha,
#     )
#     return feed, seed
#
#
# def _feed(*, page, seed, limit, viewer=None, taste_vec=None, alpha=0.0):
#     """post id 목록을 페이지 수만큼 잘라서 DB에서 post를 불러오는 함수."""
#     # now = timezone.now()
#     naive = datetime(2026, 5, 1, 0, 0, 0)  # todo
#     now = timezone.make_aware(naive)
#     all_ids = _get_or_build_order(now, seed, viewer=viewer,
#                                   taste_vec=taste_vec, alpha=alpha)
#
#     start = page * limit
#     page_ids = all_ids[start:start + limit]
#     if not page_ids:
#         return []
#
#     posts = Post.objects.select_related("user").filter(id__in=page_ids)
#     order = {pid: idx for idx, pid in enumerate(page_ids)}
#     return sorted(posts, key=lambda p: order[p.id])
#
#
# def _get_or_build_order(now, seed, *, viewer=None, taste_vec=None, alpha=0.0):
#     """redis 에서 정렬된 id 리스트를 꺼내거나, 없으면 만들어 저장."""
#     uid = viewer.id if (viewer is not None and viewer.is_authenticated) else "anon"
#     key = _explore_list_key(uid)
#     cached = cache.get(key)
#     if cached is not None and cached["seed"] == seed:
#         return cached["ids"]
#
#     feed_ids = _build_full_order(now, seed, taste_vec=taste_vec, alpha=alpha)
#     cache.set(key, {"seed": seed, "ids": feed_ids}, CACHE_TTL)
#     return feed_ids
#
#
# def _explore_list_key(uid):
#     return f"feed:{uid}"
#
#
# def _build_full_order(now, seed, *, taste_vec=None, alpha=0.0):
#     orders = {
#         "M": main_order(now, seed, taste_vec=taste_vec, alpha=alpha),
#         "N": new_order(now, seed, taste_vec=taste_vec, alpha=alpha),
#         "S": sub_order(now, seed, taste_vec=taste_vec, alpha=alpha),
#     }
#     used = set()
#     feed_ids = []
#     cursor = {"M": 0, "N": 0, "S": 0}
#
#     while True:
#         added = False
#         for slot in SLOT_LAYOUT:
#             bucket = orders[slot]
#             i = cursor[slot]
#             if i < len(bucket):
#                 cursor[slot] = i + 1
#                 post = bucket[i]
#                 if post.id not in used:
#                     used.add(post.id)
#                     feed_ids.append(post.id)
#                     added = True
#         if not added:
#             break
#
#     return feed_ids
#
#
