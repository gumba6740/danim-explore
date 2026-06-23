"""
코드북 품질 재기 (3단계: 품질 지표)
==================================
구워서 저장한 codebook.npy 가 "얼마나 잘 갈렸나"를 숫자로 잰다.
굽기 단계와 분리해서, 저장된 자산 그 자체를 정직하게 평가한다.

두 지표:
  - inertia   : 점들이 자기 칸 중심에 바짝 붙은 정도(작을수록 뭉침).
                절대값은 의미 없음 → K끼리·판끼리 비교용. 참고로 같이 저장.
  - silhouette: 칸이 깔끔하게 갈렸나. -1~+1, 클수록 좋음. ← '정확도' 역할.
                0.5↑ 양호 / 0.2↓ 칸이 흐릿 (대략적 관례).

주의: inertia 의 '진짜 최솟값'은 NP-난해라 못 구한다. 그래서 절대 점수("100점 만점에
      몇 점")는 만들 수 없고, silhouette 처럼 척도가 박힌 지표로 갈음한다.

산출물:
  codebook_quality.json - inertia, silhouette, 칸 크기 요약

실행:
    python manage.py shell < eval_codebook.py
"""

import json
import numpy as np
from sklearn.metrics import silhouette_score

# ── 프로젝트에 맞게 경로만 ──────────────────────────────
from apps.posts.models import PostEmbedding
# ───────────────────────────────────────────────────────

# ── 손잡이 ──────────────────────────────────────────────
FIELD = "embedding"            # 1·2단계와 반드시 동일하게!
CODEBOOK_PATH = "codebook.npy" # bake_codebook.py 가 구워둔 코드북
# ───────────────────────────────────────────────────────


def normalize_rows(m):
    """각 벡터를 길이 1로 (단위구 표면에 올림)."""
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def main():
    # 1) 구워둔 코드북 로드 (이미 단위벡터로 저장돼 있음)
    centroids = np.load(CODEBOOK_PATH)
    K = centroids.shape[0]

    # 2) 임베딩 로드
    rows = list(PostEmbedding.objects.filter(**{f"{FIELD}__isnull": False}))
    if not rows:
        print(f"!! {FIELD} 가 채워진 게시글이 없습니다.")
        return
    X = normalize_rows(np.asarray([getattr(r, FIELD) for r in rows], dtype="float64"))
    n = X.shape[0]
    print(f"[로드] 게시글 {n}개, 코드워드 {K}개")

    # 3) 각 글을 가장 가까운 코드워드에 배정 (= k-means '배정' 단계 한 번)
    sims = X @ centroids.T                 # 코사인 유사도 (둘 다 단위벡터)
    labels = np.argmax(sims, axis=1)

    # 4) inertia = 자기 중심까지 거리제곱 합. 단위벡터라 dist² = 2 - 2·sim
    best_sim = sims[np.arange(n), labels]
    inertia = float(np.sum(2.0 - 2.0 * best_sim))

    # 5) silhouette = 칸이 갈린 정도(척도 박힌 지표). 칸 2개 이상에 점이 있어야 계산됨
    n_used = len(np.unique(labels))
    if n_used < 2:
        sil = None
        print("!! 사용된 칸이 1개뿐이라 silhouette 계산 불가")
    else:
        sil = float(silhouette_score(X, labels))

    # 6) 칸 크기 요약
    sizes = np.bincount(labels, minlength=K)
    out = {
        "field": FIELD, "n_posts": n, "K": K,
        "inertia": round(inertia, 4),
        "silhouette": round(sil, 4) if sil is not None else None,
        "cluster_sizes": {
            "min": int(sizes.min()),
            "median": int(np.median(sizes)),
            "max": int(sizes.max()),
            "empty": int((sizes == 0).sum()),
        },
    }
    with open("codebook_quality.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 7) 화면 요약
    print(f"[inertia]    {inertia:.2f}   (작을수록 뭉침; K끼리 비교용)")
    if sil is not None:
        print(f"[silhouette] {sil:.3f}   (클수록 잘 갈림; 0.5↑ 양호)")
    print(f"[칸 크기]    최소 {sizes.min()} / 중앙값 {int(np.median(sizes))} / 최대 {sizes.max()}"
          + (f" / 빈 칸 {(sizes == 0).sum()}개" if (sizes == 0).any() else ""))
    print("\n저장 완료: codebook_quality.json")


main()