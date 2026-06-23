from apps.comments.models import Comment
from apps.interactions.models import PostClick, PostLike, PostBookmark


def run():
    click_count = PostClick.objects.count()
    like_count = PostLike.objects.count()
    comment_count = Comment.objects.count()
    bookmark_count = PostBookmark.objects.count()

    PostClick.objects.all().delete()
    PostLike.objects.all().delete()
    Comment.objects.all().delete()
    PostBookmark.objects.all().delete()

    print(f"Click {click_count}건 삭제")
    print(f"Like {like_count}건 삭제")
    print(f"Comment {comment_count}건 삭제")
    print(f"Bookmark {bookmark_count}건 삭제")
    print("초기화 완료.")
