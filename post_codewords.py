"""
post_codewords.json 을 PostEmbedding.codewords 컬럼에 적재하는 스크립트.

- 키(ULID) = Post.id, 값 = [{"codeword": int, "weight": float}, ...] (top-3)
- codewords / codebook_version 두 컬럼만 bulk_update 로 갱신 (벡터는 안 건드림)

실행:
    python manage.py shell < post_codewords.py
"""
import json
from pathlib import Path

from django.db import transaction

from apps.posts.models import PostEmbedding

# ── 설정 ─────────────────────────────────────────
JSON_PATH = "codebook/k_80/post_codewords_80.json"   # bake_codebook.py 가 만든 파일 경로
VERSION = "v1"                       # 코드북 버전. 모델 default(codebook_version) 와 맞추기
BATCH = 500                          # bulk_update 묶음 크기
# ────────────────────────────────────────────────

data = json.loads(Path(JSON_PATH).read_text(encoding="utf-8"))
print(f"[로드] {JSON_PATH}: 게시글 {len(data)}개")

post_ids = list(data.keys())

# 해당 게시글의 PostEmbedding 만 한 번에 조회 → post_id 로 매핑
by_post = {
    str(e.post_id): e
    for e in PostEmbedding.objects.filter(post_id__in=post_ids)
}
print(f"[매칭] PostEmbedding 존재: {len(by_post)} / {len(post_ids)}")

to_update = []
missing = []
for pid, codewords in data.items():
    emb = by_post.get(str(pid))
    if emb is None:
        missing.append(pid)          # 임베딩이 아직 없는 게시글 (스킵)
        continue
    emb.codewords = codewords        # 리스트 그대로 JSONField 에 저장
    emb.codebook_version = VERSION
    to_update.append(emb)

# 전체 all-or-nothing 으로 묶어서 갱신
updated = 0
with transaction.atomic():
    for i in range(0, len(to_update), BATCH):
        chunk = to_update[i:i + BATCH]
        PostEmbedding.objects.bulk_update(chunk, ["codewords", "codebook_version"])
        updated += len(chunk)

print(f"[완료] PostEmbedding {updated}개 갱신 (version={VERSION})")
if missing:
    print(f"[경고] 임베딩 없어서 스킵: {len(missing)}개")
    print("       예시:", ", ".join(missing[:5]))

# ── 검증: 무작위 1건 다시 읽어서 확인 ──────────────
if to_update:
    sample = PostEmbedding.objects.filter(
        post_id=to_update[0].post_id
    ).values("post_id", "codebook_version", "codewords").first()
    print("[검증] 샘플:", sample)