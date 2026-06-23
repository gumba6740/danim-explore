"""이제는 쓰지 않는 함수들"""

# def build_taste_vec(user):
"""양자화를 도입하기 전에 유저 취향을 계산했던 함수"""
#     scores = {}
#
#     # scores에 {post: 점수} 꼴로 저장. 점수는 상호작용 가중치들의 합
#     def add(post, kind, created_at):
#         vec = getattr(post, "vector", None)
#         if vec is None or vec.embedding is None:
#             return
#         age_days = (timezone.now() - created_at).days
#         # 상호작용에 시간감쇠를 넣어 오래됐을수록 취향 벡터에 덜 반영
#         w = TASTE_WEIGHTS[kind] * _sigmoid_decay(age_days, center=60, scale=2)
#         scores[post] = scores.get(post, 0) + w
#
#     # 유저 개인의 상호작용 내역을 가져와서 add() 계산
#     for like in PostLike.objects.filter(user=user).select_related("post__vector"):
#         add(like.post, "like", like.created_at)
#     for c in Comment.objects.filter(user=user).select_related("post__vector"):
#         add(c.post, "comment", c.created_at)
#     for clk in PostClick.objects.filter(user=user).select_related("post__vector"):
#         add(clk.post, "click", clk.created_at)
#     for bookmark in PostBookmark.objects.filter(user=user).select_related("post__vector"):
#         add(bookmark.post, "bookmark", bookmark.created_at)
#
#     if not scores:
#         return None
#
#     # 파이썬 리스트를 numpy array로 만들어 for문 없이 한번에 계산
#     vecs = np.stack([np.asarray(p.vector.embedding) for p in scores])
#     weights = np.asarray(list(scores.values()))
#     # 곱셈 하려고 weights도 세로로 쌓아 vecs와 모양을 맞춰줌
#     taste = (vecs * weights[:, None]).sum(axis=0) / weights.sum()
#     return taste / np.linalg.norm(taste)