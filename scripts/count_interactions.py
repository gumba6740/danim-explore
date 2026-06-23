from apps.comments.models import Comment
from apps.interactions.models import PostClick, PostLike, PostBookmark


def run():
    print(f"PostClick {PostClick.objects.count()}건")
    print(f"PostLike {PostLike.objects.count()}건")
    print(f"PostComment {Comment.objects.count()}건")
    print(f"PostBookmark {PostBookmark.objects.count()}건")