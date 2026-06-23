# apps/posts/management/commands/seed_locations.py
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.posts.models import Location


# (지역명, 위도 y, 경도 x) — 시청/시 대표점 기준, 카카오맵에 찍으면 해당 시 도심에 들어감
# x = 경도(longitude), y = 위도(latitude) — 카카오 좌표 규약과 동일
LOCATIONS = [
    # 특별시 / 광역시
    ("서울특별시", 37.566535, 126.977969),
    ("부산광역시", 35.179554, 129.075642),
    ("대구광역시", 35.871435, 128.601445),
    ("인천광역시", 37.456256, 126.705206),
    ("광주광역시", 35.160467, 126.851392),
    ("대전광역시", 36.350412, 127.384548),
    ("울산광역시", 35.539797, 129.311360),
    ("세종특별자치시", 36.480132, 127.289021),
    # 경기
    ("수원시", 37.263573, 127.028601),
    ("고양시", 37.658359, 126.831969),
    ("용인시", 37.241086, 127.177554),
    ("성남시", 37.420024, 127.126656),
    ("부천시", 37.503540, 126.766020),
    ("안양시", 37.394329, 126.956823),
    # 강원
    ("춘천시", 37.881266, 127.729829),
    ("강릉시", 37.752080, 128.875900),
    ("속초시", 38.207013, 128.591767),
    ("원주시", 37.341910, 127.920810),
    # 충북 / 충남
    ("청주시", 36.642434, 127.489031),
    ("충주시", 36.991020, 127.925960),
    ("천안시", 36.815136, 127.113930),
    ("아산시", 36.789772, 127.002375),
    ("공주시", 36.446550, 127.119050),
    # 전북 / 전남
    ("전주시", 35.824215, 127.147977),
    ("군산시", 35.967600, 126.736900),
    ("여수시", 34.760402, 127.662275),
    ("순천시", 34.950640, 127.487520),
    ("목포시", 34.811850, 126.392150),
    # 경북 / 경남
    ("포항시", 36.019020, 129.343500),
    ("경주시", 35.856195, 129.224732),
    ("안동시", 36.568430, 128.729550),
    ("창원시", 35.227980, 128.681750),
    ("김해시", 35.228574, 128.889222),
    ("진주시", 35.180350, 128.107670),
    ("통영시", 34.854300, 128.433200),
    # 제주
    ("제주시", 33.499621, 126.531188),
    ("서귀포시", 33.253994, 126.560002),
]


class Command(BaseCommand):
    help = "주요 시 단위 Location 더미 데이터를 넣는다 (1글 1지역 테스트용)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="기존 Location을 모두 지우고 다시 넣는다. (PostSpot이 참조 중이면 막힘)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            count = Location.objects.count()
            Location.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"기존 Location {count}건 삭제"))
            return

        created, skipped = 0, 0
        for name, lat, lng in LOCATIONS:
            # place_name 기준 멱등(idempotent) — 이미 있으면 건너뜀
            obj, is_created = Location.objects.get_or_create(
                place_name=name,
                defaults={
                    "address_name": name,
                    "road_address_name": name,
                    "x": Decimal(str(lng)),   # 경도
                    "y": Decimal(str(lat)),   # 위도
                },
            )
            if is_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"완료 — 생성 {created}건, 기존 유지 {skipped}건, 총 {Location.objects.count()}건"
            )
        )