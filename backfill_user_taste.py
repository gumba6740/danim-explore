"""
유저 취향(codeword_counts) 재계산 + 백필
=========================================
유저가 상호작용한 글들의 codewords를, 신호 세기로 가중해 칸별로 합산한다.
결과 = UserTaste.codeword_counts  (유저의 "어느 칸을 얼마나 좋아하나" 분포)

방식 B(매번 전체 재계산): 유저의 현재 살아있는 상호작용을 다 모아 한 방에 계산.
  → 클릭 7일 만료가 자동 반영됨(만료된 PostClick 행은 이미 없으니까).
  → 백필이든 실시간이든 recompute_user_taste(user) 하나만 부르면 됨.

실행(백필, 상호작용 있는 유저 전체):
    python manage.py shell < backfill_user_taste.py
"""

from collections import defaultdict
from django.contrib.auth import get_user_model
from django.db import transaction

# ── 프로젝트 경로 ───────────────────────────────────────
from apps.posts.models import PostEmbedding
from apps.users.models import UserTaste            # UserTaste 위치 다르면 수정
from apps.interactions.models import PostLike, PostBookmark, PostClick
from apps.comments.models import Comment
# ───────────────────────────────────────────────────────

# ── 신호 가중치 (나중에 조절하는 손잡이) ─────────────────
W_LIKE = 3.0       # 좋아요: 강한 영구 신호
W_BOOKMARK = 3.0   # 북마크: 강한 의도 신호
W_COMMENT = 3.0    # 댓글: 강한 참여 신호
W_CLICK = 1.0      # 클릭: 약한 신호(실수 가능 + 7일 만료)

VERSION = "v1"
ALPHA_FULL_AT = 10  # 상호작용한 글이 이만큼이면 개인화 alpha=1.0 (cold start 완충)
# ───────────────────────────────────────────────────────


def _collect_post_weights(user):
    """이 유저의 (글 → 누적 신호 가중치). 같은 글을 여러 방식으로 만지면 합산됨
    (좋아요+댓글 = 6.0). 한 신호 안에서는 글 단위로 1번만 침(같은 글 여러 클릭/댓글은 1회)."""
    pw = defaultdict(float)
    for pid in PostLike.objects.filter(user=user).values_list("post_id", flat=True):
        pw[pid] += W_LIKE
    for pid in PostBookmark.objects.filter(user=user).values_list("post_id", flat=True):
        pw[pid] += W_BOOKMARK
    for pid in Comment.objects.filter(user=user).values_list("post_id", flat=True).distinct():
        pw[pid] += W_COMMENT
    for pid in PostClick.objects.filter(user=user).values_list("post_id", flat=True).distinct():
        pw[pid] += W_CLICK
    return pw


def recompute_user_taste(user):
    """유저 한 명의 codeword_counts를 처음부터 다시 계산해 저장.
    ★ 이 함수를 service 모듈로 옮겨서, 상호작용 생길 때마다 호출하면 실시간 갱신도 됨."""
    pw = _collect_post_weights(user)

    counts = defaultdict(float)
    if pw:
        # 만진 글들의 codewords를 한 번에 가져와 칸별 합산
        rows = PostEmbedding.objects.filter(
            post_id__in=list(pw.keys())
        ).values_list("post_id", "codewords")
        for post_id, codewords in rows:
            sig = pw[post_id]
            for cw, weight in (codewords or {}).items():
                counts[cw] += weight * sig

    # 개인화 강도 alpha: 만진 글 수에 따라 0~1로 완만히 상승 (cold start 완충)
    n_posts = len(pw)
    alpha = min(1.0, n_posts / ALPHA_FULL_AT) if n_posts else 0.0

    counts = {cw: round(v, 4) for cw, v in counts.items()}

    taste, _ = UserTaste.objects.update_or_create(
        user=user,
        defaults={
            "codeword_counts": counts,
            "codebook_version": VERSION,
            "alpha": alpha,
        },
    )
    return taste, n_posts


def main():
    User = get_user_model()

    # 상호작용이 하나라도 있는 유저만 추리기
    user_ids = set()
    user_ids.update(PostLike.objects.values_list("user_id", flat=True).distinct())
    user_ids.update(PostBookmark.objects.values_list("user_id", flat=True).distinct())
    user_ids.update(PostClick.objects.values_list("user_id", flat=True).distinct())
    user_ids.update(
        Comment.objects.filter(user__isnull=False).values_list("user_id", flat=True).distinct()
    )
    user_ids.discard(None)
    print(f"[대상] 상호작용 있는 유저 {len(user_ids)}명")

    done = 0
    for user in User.objects.filter(id__in=user_ids):
        with transaction.atomic():
            taste, n = recompute_user_taste(user)
        done += 1
        if done <= 5:  # 처음 몇 명은 검수용으로 찍기
            top = sorted(taste.codeword_counts.items(), key=lambda x: -x[1])[:5]
            preview = ", ".join(f"칸{cw}:{v}" for cw, v in top)
            print(f"  user={user.id} | 만진글 {n}개 | alpha={taste.alpha:.2f} | 상위칸 {preview}")
    print(f"[완료] {done}명 갱신")


main()