from django.db import models

from apps.core.utils.ulid import generate_ulid


class BaseModel(models.Model):
    """updated_at이 필요없는 경우 상속받아 사용"""

    id = models.CharField(
        primary_key=True, max_length=26, default=generate_ulid, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["id"]

