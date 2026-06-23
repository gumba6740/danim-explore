import random

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.models import BaseModel



class Location(BaseModel):
    address_name = models.CharField(max_length=255)
    road_address_name = models.CharField(max_length=255)
    place_name = models.CharField(max_length=255)
    x = models.DecimalField(max_digits=17, decimal_places=14)
    y = models.DecimalField(max_digits=17, decimal_places=14)

    class Meta:
        db_table = "locations"


def get_random():
    return random.random()


class Post(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    title = models.CharField(max_length=100)
    content = models.TextField(blank=True, default="")
    thumbnail = models.TextField(blank=True, default="")
    # 추가
    like_count = models.PositiveIntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    random_score = models.FloatField(default=get_random, db_index=True)

    class Meta:
        db_table = "posts"


class PostEmbedding(BaseModel):
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name="vector")
    raw_embedding = VectorField(dimensions=1024, null=True, blank=True)
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    codewords = models.JSONField(default=dict, blank=True)
    codebook_version = models.CharField(max_length=16, default="v1", blank=True)


class PostSpot(BaseModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="spots")
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="post_spots"
    )
    content = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField()

    class Meta:
        db_table = "post_spots"
        ordering = ["order"]


class PostSpotImage(BaseModel):
    post_spot = models.ForeignKey(
        PostSpot, on_delete=models.CASCADE, related_name="images"
    )
    img_key = models.TextField()
    original_img = models.TextField()
    img_order = models.PositiveIntegerField()

    class Meta:
        db_table = "post_spot_images"
        ordering = ["img_order"]
