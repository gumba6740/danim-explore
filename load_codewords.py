"""
코드워드 배정을 DB에 적재
==========================
bake_codebook.py 가 만든 post_codewords.json 을 읽어서
각 PostEmbedding.codewords 필드에 저장한다.

저장 형태: {"12": 0.5, "47": 0.3, "8": 0.2}   (코드워드ID → 가중치, 합 1)
  - bake 결과는 [{"codeword":12,"weight":0.5}, ...] 리스트인데,
    추천에서 쓰기 편하게 {코드워드: 가중치} 맵으로 바꿔 저장.

실행:
    python manage.py shell < load_codewords.py
"""

import json
from django.db import transaction

# ── 프로젝트에 맞게 경로만 ──────────────────────────────
from apps.posts.models import PostEmbedding
# ───────────────────────────────────────────────────────

VERSION = "v1"
JSON_PATH = "post_codewords.json"
BATCH = 200


def main():
    with open(JSON_PATH, encoding="utf-8") as f:
        raw = json.load(f)   # { "<post_id>": [ {codeword, weight}, ... ] }
    print(f"[로드] post_codewords.json: {len(raw)}건")

    # post_id(문자열) → {코드워드(문자열): 가중치}
    # JSONField 키는 어차피 문자열로 저장되니 코드워드도 str로 통일
    cw_map = {
        pid: {str(item["codeword"]): item["weight"] for item in items}
        for pid, items in raw.items()
    }

    # 해당 post들의 PostEmbedding 한 번에 가져오기
    rows = list(PostEmbedding.objects.filter(post_id__in=list(cw_map.keys())))
    print(f"[매칭] PostEmbedding {len(rows)}건")

    missing = set(cw_map.keys()) - {str(r.post_id) for r in rows}
    if missing:
        print(f"  ⚠ json에는 있는데 PostEmbedding이 없는 post {len(missing)}건 (건너뜀)")

    updated = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        for r in batch:
            r.codewords = cw_map.get(str(r.post_id), {})
            r.codebook_version = VERSION
        with transaction.atomic():
            PostEmbedding.objects.bulk_update(batch, ["codewords", "codebook_version"])
        updated += len(batch)
    print(f"[저장] {updated}건 갱신 완료 (version={VERSION})")

    # 검수: 아무거나 하나 찍어보기
    sample = PostEmbedding.objects.exclude(codewords={}).select_related("post").first()
    if sample:
        print("\n[검수 샘플]")
        print("  제목:", sample.post.title)
        print("  codewords:", sample.codewords)
        print("  version:", sample.codebook_version)


main()