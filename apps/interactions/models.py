from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

from apps.core.models import BaseModel
from apps.posts.models import Post



class PostLike(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="post_likes",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")

    class Meta:
        db_table = "post_like"
        indexes = [models.Index(fields=["user", "post"])]
        unique_together = (("user", "post"),)   # CommentLike랑 같은 패턴


class PostImpression(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="impressions",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="impressions")
    dwell_ms = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "post_impression"
        indexes = [
            models.Index(fields=["user", "post"]),
            models.Index(fields=["user", "created_at"]),   # 7일 필터 + cron 정리
        ]


class PostClick(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clicks",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="clicks")

    class Meta:
        db_table = "post_click"
        indexes = [
            models.Index(fields=["user", "post"]),
            models.Index(fields=["user", "created_at"]),
        ]

class Follow(BaseModel):
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follows")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="followed_by")

    class Meta:
        db_table = "follow"
        indexes = [models.Index(fields=["follower", "author"])]

class PostBookmark(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="bookmarks")

    class Meta:
        db_table = "post_bookmark"
        indexes = [models.Index(fields=["user", "post"])]
        unique_together = (("user", "post"),)