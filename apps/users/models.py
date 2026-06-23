from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from pgvector.django import VectorField

from apps.core.models import BaseModel


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """일반 유저 생성"""
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """super_user 생성"""
        email = self.normalize_email(email)
        user = self.create_user(email, password=password, **extra_fields)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        return user


class LoginType(models.TextChoices):
    EMAIL = "email"
    KAKAO = "kakao"
    GOOGLE = "google"


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    login_type = models.CharField(
        max_length=10, choices=LoginType.choices, default=LoginType.EMAIL
    )
    email = models.EmailField(max_length=255, unique=True)
    nickname = models.CharField(null=False, unique=True, max_length=20)
    name = models.CharField(null=False, max_length=20)
    phone_number = models.CharField(null=True, max_length=11)
    birth_day = models.DateField(null=False, blank=False)
    profile_img = models.TextField(null=True, blank=True)
    intro = models.CharField(null=True, max_length=100)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = [
        "nickname",
        "name",
        "birth_day",
    ]

    objects = UserManager()

    class Meta:
        db_table = "users"


class UserTaste(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="taste")
    codeword_counts = models.JSONField(default=dict)
    codebook_version = models.CharField(max_length=16, default="v1")
    alpha = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)