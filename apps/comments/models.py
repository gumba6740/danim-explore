from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

from apps.core.models import BaseModel
from apps.posts.models import Post



class Comment(BaseModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="comments",
    )
    content = models.CharField(max_length=100, null=True, blank=True)
    img_key = models.CharField(max_length=255, null=True, blank=True)
    original_img = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "comment"
        indexes = [models.Index(fields=["post", "user"])]


class CommentLike(BaseModel):
    comment = models.ForeignKey(
        Comment, on_delete=models.CASCADE, related_name="comment_likes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="comment_likes",
    )

    class Meta:
        db_table = "comment_like"
        indexes = [models.Index(fields=["comment", "user"])]
        unique_together = (("comment", "user"),)
