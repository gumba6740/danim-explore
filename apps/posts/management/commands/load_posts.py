"""
posts.json 을 읽어 Post + PostSpot 을 생성하는 management command.

배치 위치: apps/posts/management/commands/load_posts.py
실행:
    python manage.py load_posts
    python manage.py load_posts --input data/posts.json

전제
- posts.json 한 줄 형태: {"email": ..., "location": "수원시", "title": ..., "content": ...}
- User PK는 ULID라서 email 로 조회해 매칭
- PostSpot.location 은 on_delete=PROTECT → place_name 으로 실제 Location 을 찾아 연결
- embedding 은 여기서 채우지 않음(저장 후 별도로 계산). null 로 남김
- PostSpotImage 는 이 단계에서 다루지 않음(Post/PostSpot 채운 뒤 결정)
"""

import json
import random
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.posts.models import Location, Post, PostSpot, PostSpotImage  # 경로 다르면 수정

User = get_user_model()


# ─────────────────────────────────────────────────────────────
# 도시 로고 경로.  static/logos/{place_name}.png 형태로 저장돼 있음.
# 운영 환경 바뀌어도 안 깨지게 절대경로가 아닌 STATIC_URL 기준 상대 URL 로 저장.
# ─────────────────────────────────────────────────────────────
def logo_for(place_name: str) -> str:
    return f"/static/logos/{place_name}.png"


# created_at 랜덤 범위: 2026-02-01 ~ 2026-04-30
_START = datetime(2026, 2, 1, 0, 0, 0)
_END = datetime(2026, 4, 30, 23, 59, 59)
_SPAN_SECONDS = int((_END - _START).total_seconds())


def random_created_at():
    dt = _START + timedelta(seconds=random.randint(0, _SPAN_SECONDS))
    if settings.USE_TZ:
        return timezone.make_aware(dt)
    return dt


class Command(BaseCommand):
    help = "posts.json 을 읽어 Post 와 PostSpot 을 생성합니다."

    def add_arguments(self, parser):
        parser.add_argument("--input", default="posts.json")

    @transaction.atomic
    def handle(self, *args, **options):
        path = options["input"]
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"파일을 찾을 수 없습니다: {path}")

        # email -> User, place_name -> Location 미리 한 번에 조회
        emails = {r["email"] for r in rows}
        users = {u.email: u for u in User.objects.filter(email__in=emails)}

        names = {r["location"] for r in rows if r.get("location")}
        locations = {}
        for loc in Location.objects.filter(place_name__in=names):
            # 같은 place_name 중복이면 첫 번째 것 사용
            locations.setdefault(loc.place_name, loc)

        created = 0
        skipped = 0
        for r in rows:
            user = users.get(r["email"])
            place = r.get("location")
            loc = locations.get(place)

            # User 없거나 Location(PROTECT) 못 찾으면 건너뜀
            if user is None or loc is None:
                skipped += 1
                continue

            post = Post.objects.create(
                user=user,
                title=r["title"][:100],
                content=r.get("content", ""),
                thumbnail=logo_for(place),
                like_count=random.randint(1, 5000),
                comment_count=random.randint(0, 100),
                view_count=random.randint(50, 500_000),
                # embedding 은 저장 후 별도 계산 → null 유지
            )

            # created_at(auto_now_add) 우회: 생성 직후 update 로 덮어쓰기.
            # updated_at 도 같이 맞춰 생성/수정 시각이 어긋나지 않게 함.
            dt = random_created_at()
            Post.objects.filter(pk=post.pk).update(created_at=dt, updated_at=dt)

            spot = PostSpot.objects.create(
                post=post,
                location=loc,
                content="",  # 글당 장소 1곳. 필요하면 r["content"] 로 바꿔도 됨
                order=1,
            )

            PostSpotImage.objects.create(
                post_spot=spot,
                img_key=logo_for(place),
                original_img=f"{place}.png",
                img_order=1,
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"적재 완료 — Post {created}개 생성, 건너뜀 {skipped}개")
        )