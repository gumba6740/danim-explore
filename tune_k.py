"""
적정 K 찾기 (코드북 굽기 1단계: K 튜닝)
======================================
칸을 몇 개로 쪼갤지(K)를 정하는 단계. 코드북을 굽기 전에 딱 한 번 돌린다.

여러 K 후보로 k-means를 돌려보고, K마다 두 숫자를 잰다:
  - inertia   : 점들이 자기 중심에 얼마나 바짝 붙었나(작을수록 뭉침).
                단, K를 키우면 무조건 작아져서 절대값만으론 K를 못 정함.
                → "더 키워도 확 안 줄어드는 꺾이는 지점(엘보)"을 본다.
  - silhouette: 칸이 얼마나 깔끔하게 갈렸나. -1~+1, 클수록 좋음(0.5↑ 양호).
                K를 키운다고 무조건 오르지 않아서, 적정 K를 직접 가리킨다.

핵심: inertia는 '엘보'로, silhouette은 '최고점'으로 본다. 둘이 가리키는 K를
      같이 놓고, 사람이 최종 결정한다(기계가 자동으로 못 정함).

산출물:
  k_tuning.json - K 후보별 inertia, silhouette + 추천 K (사람 확인용)

실행:
    python manage.py shell < tune_k.py
"""

import json
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ── 프로젝트에 맞게 경로만 ──────────────────────────────
from apps.posts.models import PostEmbedding
# ───────────────────────────────────────────────────────

# ── 손잡이 ──────────────────────────────────────────────
K_CANDIDATES = [40, 60, 80, 100, 120, 140]  # 시험해 볼 칸 개수들
FIELD = "embedding"  # 코드북 굽기·추천에서 쓰는 거랑 반드시 동일하게!
SEED = 42            # 재현성 고정(매번 같은 결과)
# ───────────────────────────────────────────────────────


def normalize_rows(m):
    """각 벡터를 길이 1로 (단위구 표면에 올림)."""
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def main():
    rows = list(PostEmbedding.objects.filter(**{f"{FIELD}__isnull": False}))
    if not rows:
        print(f"!! {FIELD} 가 채워진 게시글이 없습니다.")
        return

    X = normalize_rows(np.asarray([getattr(r, FIELD) for r in rows], dtype="float64"))
    n, dim = X.shape
    print(f"[로드] 게시글 {n}개, 차원 {dim}, 벡터={FIELD}\n")

    results = []
    for K in K_CANDIDATES:
        if K >= n:
            print(f"  K={K:>3} 는 게시글 수({n})보다 커서 건너뜀")
            continue
        km = KMeans(n_clusters=K, n_init=10, random_state=SEED)
        labels = km.fit_predict(X)
        # 단위벡터라 유클리드 silhouette ≈ 코사인 기준. K끼리 비교만 하면 됨.
        sil = float(silhouette_score(X, labels))
        results.append({
            "K": K,
            "inertia": round(float(km.inertia_), 4),
            "silhouette": round(sil, 4),
        })
        print(f"  K={K:>3}  inertia={km.inertia_:>10.2f}  silhouette={sil:.3f}")

    if not results:
        print("!! 시험할 수 있는 K 후보가 없습니다.")
        return

    # silhouette 최고 K = 참고용 추천값. 최종은 엘보까지 같이 보고 사람이 결정.
    best = max(results, key=lambda r: r["silhouette"])
    out = {
        "field": FIELD, "n_posts": n, "dim": dim,
        "candidates": results,
        "suggested_K": best["K"],
    }
    with open("k_tuning.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n[추천] silhouette 최고는 K={best['K']} (={best['silhouette']:.3f})")
    print("→ k_tuning.json 에서 inertia 꺾이는 지점(엘보)과 silhouette 최고점을 함께 보고 K 결정.")
    print("  정한 K 를 bake_codebook.py 의 K 에 넣고 다음 단계로.")


main()