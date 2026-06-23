"""
발표·테스트 전용 URL.
프로젝트 urls.py 에서:
    path("api/demo/", include("apps.feed.demo_urls")),
처럼 묶어 둔다. 배포용 라우트와 분리.
"""
from django.urls import path

from . import views as views

urlpatterns = [
    path("", views.demo_page, name="demo-page"),
    path("feed/", views.feed_list, name="demo-feed"),
    path("users/", views.demo_users, name="demo-users"),
    path("posts/<str:post_id>/", views.post_detail, name="demo-post-detail"),
    path("posts/<str:post_id>/like/", views.add_like, name="demo-like"),
    path("posts/<str:post_id>/comment/", views.add_comment, name="demo-comment"),
    path("posts/<str:post_id>/bookmark/", views.add_bookmark, name="demo-bookmark"),
]