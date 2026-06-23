"""
코드북 굽기 (Plan B: 고정 코드북 + 카운트)
==========================================
도시 뺀 깨끗한 임베딩에 k-means를 한 번 돌려 코드워드 K개를 만들고 고정한다.
일회성 준비 작업 — 한 번 구워 저장하면 계속 재사용한다.

이 단계의 목적: 코드북을 만들고, 80개 칸이 "주제로 의미 있게" 갈렸는지 눈으로 확인.
  → codebook_meta.json 을 열어서 각 코드워드 대표 제목이 한 주제로 모였나 보는 게 핵심.

산출물:
  codebook.npy        - centroid K개 (K x dim). 추천/배정에 쓰는 고정 자산.
  codebook_meta.json  - 버전, K, 각 코드워드 대표 제목 5개 (사람 확인용)
  post_codewords.json - 게시글별 top-N 코드워드 + 가중치 (검수용; DB 영구저장은 다음 단계)

실행:
    python manage.py shell < bake_codebook.py
"""

import json
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

# ── 프로젝트에 맞게 경로만 ──────────────────────────────
from apps.posts.models import PostEmbedding
# ───────────────────────────────────────────────────────

# ── 손잡이 ──────────────────────────────────────────────
K = 100               # 코드워드(칸) 개수. 955개면 80이 출발점(칸당 ~12개)
TOP_N = 3            # 게시글당 배정할 코드워드 수
FIELD = "embedding"  # 센터링된 값. 순도검사·추천에서 쓰는 거랑 반드시 동일하게!
VERSION = "v1"       # 코드북 버전. 재학습하면 v2. 유저 카운트도 이 버전 기준임을 기억.
SEED = 42            # 고정하면 매번 같은 코드북이 나옴(재현성)
# ───────────────────────────────────────────────────────

BASE_DIR = Path.cwd() / "codebook"

def normalize_rows(m):
    """각 벡터를 길이 1로 (단위구 표면에 올림)."""
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def main():
    # 1) 임베딩 로드
    rows = list(
        PostEmbedding.objects
        .filter(**{f"{FIELD}__isnull": False})
        .select_related("post")
    )
    if not rows:
        print(f"!! {FIELD} 가 채워진 게시글이 없습니다.")
        return

    X = normalize_rows(np.asarray([getattr(r, FIELD) for r in rows], dtype="float64"))
    titles = [r.post.title for r in rows]
    post_ids = [r.post_id for r in rows]
    n, dim = X.shape
    print(f"[로드] 게시글 {n}개, 차원 {dim}, 벡터={FIELD}")

    # 2) k-means → centroid K개 = 코드워드
    k = min(K, n)
    suffix = f"_{k}"
    cb_dir = BASE_DIR / f"k_{k}"
    cb_dir.mkdir(parents=True, exist_ok=True)

    km = KMeans(n_clusters=k, n_init=10, random_state=SEED)
    labels = km.fit_predict(X)
    centroids = normalize_rows(km.cluster_centers_.astype("float64"))  # 표면으로 재투영
    print(f"[코드북] 코드워드 {k}개 생성")

    # 3) 코드북 저장 (고정 자산)
    np.save(cb_dir / f"codebook{suffix}.npy", centroids)

    # 4) 게시글별 top-N 코드워드 배정
    #    코사인 기준 가장 가까운 N개. 가중치는 합 1로 정규화(가까울수록 큼).
    #    → 유저가 이 글에 상호작용하면, 이 가중치만큼 칸 카운트에 더해진다.
    sims_all = X @ centroids.T  # (n, k) 각 글 ↔ 각 코드워드 코사인
    assignments = {}
    for i in range(n):
        sims = sims_all[i]
        top = np.argsort(sims)[::-1][:TOP_N]
        w = sims[top].copy()
        w[w < 0] = 0.0                       # 음수 유사도는 0
        s = w.sum()
        w = (w / s) if s > 0 else np.ones(len(top)) / len(top)
        assignments[str(post_ids[i])] = [
            {"codeword": int(c), "weight": round(float(wi), 4)}
            for c, wi in zip(top, w)
        ]
    with open(cb_dir / f"post_codewords{suffix}.json", "w", encoding="utf-8") as f:
        json.dump(assignments, f, ensure_ascii=False, indent=2)

    # 5) 메타 + 사람 확인용: 각 코드워드의 대표 제목(가장 가까운 순 5개)
    meta = {
        "version": VERSION, "K": k, "dim": dim,
        "field": FIELD, "n_posts": n, "top_n": TOP_N,
        "codewords": [],
    }
    for c in range(k):
        members = [i for i in range(n) if labels[i] == c]
        members.sort(key=lambda i: sims_all[i][c], reverse=True)
        meta["codewords"].append({
            "id": c,
            "size": len(members),
            "sample_titles": [titles[i] for i in members[:5]],
        })
    with open(cb_dir / f"codebook_meta{suffix}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 6) 화면 요약
    sizes = sorted(cw["size"] for cw in meta["codewords"])
    empty = sum(1 for s in sizes if s == 0)
    print(f"[칸 크기] 최소 {sizes[0]} / 중앙값 {sizes[len(sizes)//2]} / 최대 {sizes[-1]}"
          + (f" / 빈 칸 {empty}개" if empty else ""))
    print("\n[미리보기] 코드워드 10개:")
    for cw in meta["codewords"][:10]:
        sample = " / ".join(cw["sample_titles"][:3])
        print(f"  #{cw['id']:>2} ({cw['size']:>2}개): {sample}")

    print(f"\n저장 완료: codebook{suffix}.npy / codebook_meta{suffix}.json / post_codewords{suffix}.json")
    print(f"→ codebook_meta{suffix}.json 열어서 칸들이 주제로 깨끗하게 모였나 확인하세요.")


main()