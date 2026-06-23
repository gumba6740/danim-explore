"""
PostEmbedding 의 raw_embedding / embedding 을 생성하는 management command.

배치 위치: apps/posts/management/commands/generate_embeddings.py
실행:
    python manage.py generate_embeddings           # 새 글만 처리
    python manage.py generate_embeddings --all      # 전부 다시 인코딩

사전 설치: pip install sentence-transformers numpy

- raw_embedding : 원본 임베딩 벡터.
- embedding     : raw 에서 전역 평균을 뺀 뒤 재정규화. 실질적으로 추천에 쓰는 값.
- 전역 평균은 컬렉션 전체에 1개. 처음 한 번 계산해 파일에 저장하고 계속 재사용.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.posts.models import Post, PostEmbedding  # 경로 다르면 수정
import re

EXPECTED_DIM = 1024
MEAN_PATH = os.environ.get("EMBEDDING_MEAN_PATH", "embedding_mean.npy")



def _strip_cities(text, city_names):
    if not text:
        return text
    for name in city_names:      # 긴 이름부터 (아래서 정렬해 둠)
        text = text.replace(name, "")
    return text

def build_text(post) -> str:
    spots = list(post.spots.all())

    # 이 글에 달린 도시명 모으기 (원형 + 시/군/구/도 접미사 뗀 형태)
    city_names = set()
    for spot in spots:
        raw = spot.location.place_name
        if not raw:
            continue
        city_names.add(raw)
        base = re.sub(r"(특별시|광역시|특별자치시|특별자치도|시|군|구|도)$", "", raw)
        if base and base != raw:
            city_names.add(base)
    city_names = sorted(city_names, key=len, reverse=True)  # "충주시"를 "충주"보다 먼저 제거

    parts = [
        _strip_cities(post.title, city_names),
        _strip_cities(post.content, city_names),
    ]
    for spot in spots:
        if spot.content:
            parts.append(_strip_cities(spot.content, city_names))
        # place_name(도시명)은 더 이상 임베딩에 넣지 않음 — 위치는 Location 테이블로 따로 관리

    return "\n".join(p for p in parts if p and p.strip())


class Command(BaseCommand):
    help = "PostEmbedding 의 raw_embedding / embedding 을 생성합니다."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--model", default="BAAI/bge-m3")
        parser.add_argument("--all", action="store_true", help="전부 다시 인코딩")

    def handle(self, *args, **options):
        import numpy as np

        bs = options["batch_size"]

        qs = Post.objects.all()
        if not options["all"]:
            qs = qs.filter(vector__raw_embedding__isnull=True)
        posts = list(qs.prefetch_related("spots", "spots__location"))

        if posts:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(options["model"])
            if model.get_embedding_dimension() != EXPECTED_DIM:
                raise CommandError(f"모델 차원이 {EXPECTED_DIM}이 아닙니다.")

            self.stdout.write(f"raw 생성: {len(posts)}건")
            for i in range(0, len(posts), bs):
                batch = posts[i : i + bs]
                # normalize: 모든 벡터의 길이를 1로 맞춤. 길이 데이터는 노이즈가 많기 때문에.
                vecs = model.encode([build_text(p) for p in batch], normalize_embeddings=True)
                with transaction.atomic():
                    for p, v in zip(batch, vecs):
                        # 안전하게, 넘파이 배열을 파이썬 리스트로 변환해서 저장
                        PostEmbedding.objects.update_or_create(
                            post=p, defaults={"raw_embedding": v.tolist()}
                        )

        # if os.path.exists(MEAN_PATH):
        #     mean = np.load(MEAN_PATH)
        # else:
        #     raws = PostEmbedding.objects.filter(raw_embedding__isnull=False).values_list(
        #         "raw_embedding", flat=True
        #     )
        #     if not raws:
        #         raise CommandError("raw_embedding 이 없어 평균을 만들 수 없습니다.")
        #     mean = np.asarray(list(raws), dtype="float64").mean(axis=0)
        #     np.save(MEAN_PATH, mean)
        #     self.stdout.write(f"평균 생성 (norm={np.linalg.norm(mean):.4f})")
        #
        # # raw_embedding을 센터링하여 embedding 컬럼에 저장
        # rows = list(
        #     PostEmbedding.objects.filter(
        #         raw_embedding__isnull=False, embedding__isnull=True
        #     )
        # )
        # if rows:
        #     self.stdout.write(f"센터링: {len(rows)}건")
        #     for i in range(0, len(rows), bs):
        #         batch = rows[i : i + bs]
        #         m = np.asarray([r.raw_embedding for r in batch], dtype="float64") - mean
        #         # 노멀라이즈. 벡터를 벡터 길이로 나눔
        #         m /= np.linalg.norm(m, axis=1, keepdims=True)
        #         for r, v in zip(batch, m):
        #             r.embedding = v.tolist()
        #         PostEmbedding.objects.bulk_update(batch, ["embedding"])

        self.stdout.write(self.style.SUCCESS("완료!"))

        import os
        os._exit(0)