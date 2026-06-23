# scripts/check_sim.py
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import F, Count, Max
from apps.posts.models import Post


def run(*args):
    if not args:
        print("사용법: python manage.py runscript check_sim --script-args <post_id> [검색어]")
        return

    pid = args[0]
    search = args[1] if len(args) > 1 else "서울"

    # 합산 sim / reaction (실제 쿼리와 동일한 annotation)
    agg = (
        Post.objects.filter(id=pid)
        .annotate(
            sim=TrigramSimilarity("content", search) * 3
            + TrigramSimilarity("title", search) * 3
            + Max(TrigramSimilarity("spots__location__place_name", search)),
            reaction=F("like_count") + F("comment_count") + Count("bookmarks", distinct=True),
        )
        .select_related("user")
        .first()
    )

    if agg is None:
        print(f"[!] id={pid} 게시글 없음")
        return

    # 각 필드별 원점수 (가중치 적용 전)
    raw = (
        Post.objects.filter(id=pid)
        .annotate(
            content_sim=TrigramSimilarity("content", search),
            title_sim=TrigramSimilarity("title", search),
        )
        .values("content_sim", "title_sim")
        .first()
    )
    content_sim = raw["content_sim"] or 0.0
    title_sim = raw["title_sim"] or 0.0

    # spot별 place_name 유사도 (Max가 어느 spot에서 나왔는지 확인용)
    spot_rows = (
        Post.objects.filter(id=pid)
        .annotate(place_sim=TrigramSimilarity("spots__location__place_name", search))
        .values("spots__location__place_name", "place_sim")
    )
    place_pairs = [
        (r["spots__location__place_name"], r["place_sim"] or 0.0)
        for r in spot_rows
    ]
    place_max = max((s for _, s in place_pairs), default=0.0)

    print(f"========== 검색어: '{search}' ==========")
    print(f"id       : {pid}")
    print(f"nickname : {agg.user.nickname}")
    print(f"title    : {agg.title}")
    print("-" * 50)
    print(f"content_sim : {content_sim:.4f}  (x3 = {content_sim * 3:.4f})")
    print(f"title_sim   : {title_sim:.4f}  (x3 = {title_sim * 3:.4f})")
    print(f"place_max   : {place_max:.4f}  (가중치 없음)")
    print("-" * 50)
    print("[spot별 place_name 유사도]")
    for name, s in place_pairs:
        print(f"   {s:.4f}  <- {name}")
    print("-" * 50)
    calc = content_sim * 3 + title_sim * 3 + place_max
    print(f"수동 합산 sim : {calc:.4f}")
    print(f"ORM sim       : {agg.sim:.4f}")  # 둘이 다르면 fanout 문제 신호
    print(f"reaction      : {agg.reaction}")
    print(f"threshold(1.0) 통과: {agg.sim is not None and agg.sim >= 1.0}")