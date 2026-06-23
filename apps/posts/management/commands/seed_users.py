import random
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.posts.management.persona import user_persona

try:
    from faker import Faker

    fake = Faker("ko_KR")
except ImportError:
    fake = None

User = get_user_model()

DEFAULT_PASSWORD = "test1234!"


def make_birth_day(age: int) -> date:
    """나이로 출생일을 만든다. (연도만 정확하고 월/일은 랜덤)"""
    today = date.today()
    year = today.year - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)  # 28일까지만 써서 월말 예외 회피
    return date(year, month, day)


def make_name(index: int) -> str:
    """faker 가 있으면 한글 이름, 없으면 대체 이름."""
    if fake is None:
        return f"테스트유저{index:02d}"
    return fake.name()


class Command(BaseCommand):
    help = "테스트용 여행 SNS 유저를 DB에 생성합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="생성되는 모든 유저의 공통 비밀번호",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        created = 0
        skipped = 0

        for i, data in enumerate(user_persona, start=1):
            email = f"test_user_{i:02d}@example.com"

            # 이미 있으면 건너뛰어서 여러 번 실행해도 안전하게
            if User.objects.filter(email=email).exists():
                skipped += 1
                continue

            User.objects.create_user(
                email=email,
                password=password,
                nickname=f"여행러_{i:02d}",
                name=make_name(i),
                birth_day=make_birth_day(data["age"]),
                intro=data["persona"],
                phone_number=f"010{random.randint(10000000, 99999999)}",
                is_active=True,
                is_email_verified=True,
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"유저 생성 완료 — 새로 생성 {created}명, 건너뜀 {skipped}명")
        )
