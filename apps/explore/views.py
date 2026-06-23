# apps/feed/demo_views.py
"""
발표·테스트 전용 API.
- 인증 없이 ?email= 로 임의의 viewer를 흉내낸다 (데모 목적, ULID는 예측 불가라 이메일로 지정).
- 좋아요/댓글/북마크/클릭은 모두 INSERT-only (토글·삭제 없음).
- 상호작용 시 Post의 비정규화 카운터(like_count 등)도 같이 갱신한다.
  → 점수 함수가 raw 테이블이 아니라 이 카운터를 읽기 때문에, 갱신해야 데모에 반영된다.
"""
from pathlib import Path

from django.conf import settings
from django.db.models import F
from django.http import JsonResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.explore.services.search import search_feed
from apps.posts.models import Post
from apps.comments.models import Comment
from apps.interactions.models import PostLike, PostClick, PostBookmark

from apps.explore.services.feed_prod import get_explore_feed


# ── viewer 해석 (이메일 기준) ────────────────────────────────
def _resolve_viewer(request):
    """
    데모용 viewer 해석. ?email= 로 유저를 지정.
    ULID id는 사람이 예측·입력하기 어려워서, 발표 땐 이메일로 받는다.
    email 이 없으면 None(익명)으로 처리.
    """
    from apps.users.models import User

    email = (request.GET.get("email") or request.POST.get("email") or "").strip()
    if not email:
        return None
    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        raise Http404("해당 이메일의 유저가 없습니다.")


class _DemoViewer:
    """get_explore_feed 가 viewer.is_authenticated 를 보므로, 항상 인증된 것으로 취급."""
    def __init__(self, user):
        self._user = user
        self.id = user.id
        self.is_authenticated = True

    def __getattr__(self, name):
        return getattr(self._user, name)


def _post_brief(post):
    return {
        "post_id": str(post.id),
        "thumbnail": post.thumbnail or "",
        "title": post.title,
        "content": post.content or "",
        "view_count": post.view_count,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
    }


# ── 페이지: HTML 서빙 (템플릿 엔진 안 거침) ──────────────────
def demo_page(request):
    """list.html 을 글자 그대로 응답. 템플릿 렌더를 안 해 ${} 가 안 깨진다."""
    html = (settings.BASE_DIR / "templates" / "list.html").read_text(encoding="utf-8")
    return HttpResponse(html)


# ── 0) 테스트 유저 목록 (드롭다운용) ─────────────────────────
@require_GET
def demo_users(request):
    """
    이메일이 'demo_' 로 시작하는 유저만 반환 (발표/테스트용으로 만든 유저).
    기존 게시글 작성 유저(test...)와 구분된다.
    드롭다운을 채우는 데 쓴다.
    """
    from apps.users.models import User

    users = (
        User.objects.filter(email__startswith="demo")
        .order_by("email")
        .values("email", "nickname")
    )
    return JsonResponse({"users": list(users)})


# ── 1) 피드 리스트 ───────────────────────────────────────────
@require_GET
def feed_list(request):
    """탐색 피드 + 검색. ?email=&page=&seed=&search= 로 호출."""
    # page 변환을 맨 위로 (search/explore 둘 다 int 필요)
    try:
        page = int(request.GET.get("page", 0))
    except (ValueError, TypeError):
        page = 0

    search = (request.GET.get("search") or "").strip()
    if search:
        posts = search_feed(search, page)          # _search_feed → 공개명으로
        from apps.explore.services.search import PAGE_LIMIT
        return JsonResponse({
            "seed": None,
            "page": page,
            "has_next": len(posts) >= PAGE_LIMIT,
            "results": [_post_brief(p) for p in posts],
        })

    # ── 탐색 피드 분기 ──
    user = _resolve_viewer(request)
    viewer = _DemoViewer(user) if user is not None else None

    seed = request.GET.get("seed")
    seed = int(seed) if (seed and seed.isdigit()) else None

    posts, used_seed = get_explore_feed(viewer=viewer, page=page, seed=seed)

    from apps.explore.services.order import PAGE_SIZE
    has_next = len(posts) >= PAGE_SIZE

    return JsonResponse({
        "seed": used_seed,
        "page": page,
        "has_next": has_next,
        "results": [_post_brief(p) for p in posts],
    })


# ── 2) 게시글 상세 (클릭 기록) ───────────────────────────────
@require_GET
def post_detail(request, post_id):
    user = _resolve_viewer(request)
    post = get_object_or_404(Post, id=post_id)

    if user is not None:
        PostClick.objects.create(user=user, post=post)

    Post.objects.filter(id=post.id).update(view_count=F("view_count") + 1)
    post.refresh_from_db(fields=["view_count"])

    comments = (
        Comment.objects.filter(post=post)
        .select_related("user")
        .order_by("created_at")
        .values("id", "user__nickname", "content", "created_at")
    )

    return JsonResponse({
        "post_id": str(post.id),
        "title": post.title,
        "view_count": post.view_count,
        "comments": [
            {
                "comment_id": str(c["id"]),
                "nickname": c["user__nickname"],
                "content": c["content"],
                "created_at": c["created_at"].isoformat(),
            }
            for c in comments
        ],
    })


# ── 3) 좋아요 (INSERT-only) ──────────────────────────────────
@csrf_exempt
@require_POST
def add_like(request, post_id):
    user = _resolve_viewer(request)
    if user is None:
        return JsonResponse({"error": "email 필요"}, status=400)
    post = get_object_or_404(Post, id=post_id)

    _, created = PostLike.objects.get_or_create(user=user, post=post)
    if created:
        Post.objects.filter(id=post.id).update(like_count=F("like_count") + 1)
    post.refresh_from_db(fields=["like_count"])

    return JsonResponse({"post_id": str(post.id), "like_count": post.like_count, "created": created})


# ── 4) 댓글 (내용 없이 INSERT) ───────────────────────────────
@csrf_exempt
@require_POST
def add_comment(request, post_id):
    user = _resolve_viewer(request)
    if user is None:
        return JsonResponse({"error": "email 필요"}, status=400)
    post = get_object_or_404(Post, id=post_id)

    Comment.objects.create(user=user, post=post, content="ㅇㅇ")
    Post.objects.filter(id=post.id).update(comment_count=F("comment_count") + 1)
    post.refresh_from_db(fields=["comment_count"])

    return JsonResponse({"post_id": str(post.id), "comment_count": post.comment_count})


# ── 5) 북마크 (INSERT-only) ──────────────────────────────────
@csrf_exempt
@require_POST
def add_bookmark(request, post_id):
    user = _resolve_viewer(request)
    if user is None:
        return JsonResponse({"error": "email 필요"}, status=400)
    post = get_object_or_404(Post, id=post_id)

    _, created = PostBookmark.objects.get_or_create(user=user, post=post)
    return JsonResponse({"post_id": str(post.id), "bookmarked": True, "created": created})