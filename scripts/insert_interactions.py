"""
데모 유저에게 특정 키워드 관련 게시글로 상호작용을 심는 스크립트.

키워드(icontains)에 걸리는 게시글을 created_at 오름차순으로 정렬한 뒤,
"오래된 절반"(상위 절반)에 대해 해당 유저가
    클릭 x2, 좋아요 x1, 북마크 x1, 댓글 x1
을 한 것으로 만든다. 이후 rebuild 커맨드의 build_codeword_counts 가
이 상호작용을 읽어 코드워드 취향을 만든다.

실행 (django-extensions runscript):
    python manage.py runscript demo_interactions --script-args <유저name> <키워드>
예:
    python manage.py runscript demo_interactions --script-args a 카페
"""
from django.db.models import Q

from apps.users.models import User
from apps.posts.models import Post
from apps.interactions.models import PostLike, PostClick, PostBookmark
from apps.comments.models import Comment

CLICKS_PER_POST = 2  # 클릭은 글당 2번


def run(name, keyword):
    # 1) 대상 유저 (데모 유저 name 은 a, b, c ... 로 유니크)
    user = User.objects.filter(name=name).first()
    if user is None:
        print(f"[중단] name='{name}' 인 유저가 없습니다.")
        return

    # 2) 키워드(제목/본문 icontains)에 걸리는 글을 오래된 순으로
    posts = list(
        Post.objects
        .filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))
        .order_by("created_at")
    )
    if not posts:
        print(f"[중단] '{keyword}' 에 걸리는 게시글이 없습니다.")
        return

    # 3) 상위(= 더 오래된) 절반만 대상으로
    half = len(posts) // 2
    targets = posts[:half]
    if not targets:
        print(f"[중단] 매칭 글이 {len(posts)}개뿐이라 절반이 0개입니다. 글이 더 필요합니다.")
        return

    # 4) 상호작용 심기
    clicks = likes = bookmarks = comments = 0
    for post in targets:
        # 클릭은 이벤트 로그라 행을 여러 개 (cron 이 7일 지나면 정리)
        for _ in range(CLICKS_PER_POST):
            PostClick.objects.create(user=user, post=post)
            clicks += 1

        # 좋아요/북마크는 (user, post) 유니크 → 재실행 안전하게 get_or_create
        _, created = PostLike.objects.get_or_create(user=user, post=post)
        likes += int(created)

        _, created = PostBookmark.objects.get_or_create(user=user, post=post)
        bookmarks += int(created)

        # 댓글 1개
        Comment.objects.create(user=user, post=post, content=f"{keyword} 관련 데모 댓글")
        comments += 1

    print("=" * 40)
    print(f"유저 '{name}' / 키워드 '{keyword}'")
    print(f"매칭 글 {len(posts)}개 중 오래된 절반 {len(targets)}개에 상호작용 심음")
    print(f"  클릭 {clicks} / 좋아요 {likes} / 북마크 {bookmarks} / 댓글 {comments}")
    print("=" * 40)