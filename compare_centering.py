"""
raw vs 센터링(embedding) 정확도 비교
=====================================
같은 라벨을 두고 raw_embedding 과 embedding(센터링) 각각에 대해
"같은 주제 글끼리 실제로 더 가까이 모이는가"를 4개 지표로 잰다.
라벨러가 완벽하지 않아도, 두 컬럼에 *같은 라벨*을 쓰므로 A/B 차이(delta)는 공정하다.

지표
  1) global_mean_norm : 단위벡터들의 평균 norm = 쏠림(anisotropy) 크기.
                        등방성(랜덤) 기대치 ≈ 1/sqrt(n). 이보다 크면 쏠림 있음.
                        raw 가 크고 centered 가 0에 가까우면 "센터링이 쏠림을 제거" 한 것.
  2) avg_pairwise_cos : 아무 두 글의 평균 코사인. 0에 가까울수록 벡터가 잘 퍼져 식별력↑.
  3) silhouette       : 코사인 실루엣(known 라벨 대상). 높을수록 주제 분리 좋음. (-1~1)
  4) knn_purity@K     : 각 글의 최근접 K개 중 같은 주제 비율 평균(known 라벨 대상).
                        추천이 코사인 최근접으로 동작하므로 가장 실전에 가까운 지표.

실행:
    python manage.py shell < compare_centering.py

필요: pip install scikit-learn numpy
"""

import json
import numpy as np
from collections import Counter
from sklearn.metrics import silhouette_score

from apps.posts.models import PostEmbedding

# ── 손잡이 ───────────────────────────────────────────────
KNN_K = 10          # 최근접 이웃 수
SAMPLE_PAIRS = 200000   # avg_pairwise_cos 추정 표본(전체가 작으면 무시)
SEED = 42
OUT_PATH = "centering_compare.json"
# ─────────────────────────────────────────────────────────

# ── 주제 라벨(키워드). purity_check 보다 보강 — 별/드라이브/워케이션/가성비/역사·유적/호캉스 추가 ──
TOPIC_KEYWORDS = {
    "별밤":   ["별빛", "별 ", "별밤", "밤하늘", "은하", "별 관측", "별 감상"],
    "드라이브": ["드라이브"],
    "워케이션": ["워케이션", "워크", "업무", "일과", "워라밸", "work"],
    "가성비": ["가성비", "저렴", "알뜰", "저예산", "가심비", "저가"],
    "역사":   ["유적", "고분", "고고학", "가야", "유적지", "역사", "선사", "왕릉", "단오"],
    "호캉스": ["호캉스", "호텔", "리조트", "스위트", "풀빌라", "풀링"],
    "스쿠버": ["스쿠버", "수중", "물속", "다이빙", "스노클"],
    "템플":   ["템플스테이", "사찰", "불국사", "송광사", "절에서", "고요한"],
    "기차":   ["기차", "열차", "기차역", "철도"],
    "와인":   ["와인", "와이너리"],
    "쇼핑":   ["쇼핑", "면세점", "스타필드", "백화점", "아울렛", "킨텍스"],
    "온천":   ["온천", "스파", "사우나", "찜질"],
    "전통":   ["한옥", "전통", "하회마을", "고궁", "민속"],
    "전시":   ["전시", "미술관", "갤러리", "박물관", "아트"],
    "사진":   ["새벽", "일출", "노을", "야경", "풍경"],
    "자전거": ["자전거", "사이클", "라이딩"],
    "카페":   ["카페", "커피", "디저트", "베이커리", "브런치"],
    "맛집":   ["맛집", "식당", "국밥", "삼겹살", "흑돼지", "비빔밥", "먹거리"],
    "등산":   ["등산", "트레킹", "둘레길", "정상", "능선"],
    "바다":   ["바다", "해변", "해수욕", "해안", "해운대", "파도", "포구"],
    "캠핑":   ["캠핑", "글램핑", "텐트", "차박", "백패킹"],
    "호수":   ["호수", "저수지", "계곡"],
    "도심":   ["도심", "시내", "골목", "거리"],
}


def label_of(title):
    title = title or ""
    for label, kws in TOPIC_KEYWORDS.items():
        if any(kw in title for kw in kws):
            return label
    return "기타"


def _to_array(seq):
    """pgvector 반환형(list/np/str) 무엇이든 (n, dim) float64 배열로."""
    out = []
    for v in seq:
        if isinstance(v, str):
            v = json.loads(v)
        out.append(np.asarray(v, dtype="float64"))
    return np.vstack(out)


def normalize(m):
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def metrics(name, X, labels, known_mask, rng):
    """한 임베딩(raw 또는 centered)에 대한 지표 묶음."""
    Xn = normalize(X)
    n = len(Xn)

    # 1) 쏠림
    mean_norm = float(np.linalg.norm(Xn.mean(axis=0)))
    iso_baseline = 1.0 / np.sqrt(n)   # 등방성이면 이 근처

    # 2) 평균 페어 코사인 (표본)
    idx = np.arange(n)
    a = rng.choice(idx, size=min(SAMPLE_PAIRS, n * n), replace=True)
    b = rng.choice(idx, size=len(a), replace=True)
    sel = a != b
    pair_cos = float(np.mean(np.sum(Xn[a[sel]] * Xn[b[sel]], axis=1)))

    # known 라벨만으로 분리도 측정
    Xk = Xn[known_mask]
    yk = np.asarray(labels)[known_mask]

    # 3) 실루엣(코사인)
    sil = float(silhouette_score(Xk, yk, metric="cosine"))

    # 4) knn purity@K (known 풀 안에서)
    S = Xk @ Xk.T
    np.fill_diagonal(S, -np.inf)          # 자기 자신 제외
    nn = np.argsort(-S, axis=1)[:, :KNN_K]
    same = (yk[nn] == yk[:, None]).mean(axis=1)
    knn_purity = float(same.mean())

    return {
        "name": name,
        "global_mean_norm": round(mean_norm, 5),
        "isotropic_baseline": round(float(iso_baseline), 5),
        "avg_pairwise_cos": round(pair_cos, 5),
        "silhouette": round(sil, 5),
        f"knn_purity@{KNN_K}": round(knn_purity, 5),
    }


def main():
    rng = np.random.default_rng(SEED)

    rows = list(
        PostEmbedding.objects
        .filter(raw_embedding__isnull=False, embedding__isnull=False)
        .select_related("post")
    )
    if not rows:
        print("!! raw 와 embedding 이 둘 다 채워진 글이 없습니다.")
        return

    raw = _to_array([r.raw_embedding for r in rows])
    cen = _to_array([r.embedding for r in rows])
    labels = [label_of(r.post.title) for r in rows]
    n = len(rows)

    dist = Counter(labels)
    etc = dist.get("기타", 0)
    known_mask = np.asarray([l != "기타" for l in labels])
    n_known = int(known_mask.sum())

    print(f"[데이터] 글 {n}개 / known 라벨 {n_known}개 / 기타 {etc}개({etc/n:.0%}) / 차원 {raw.shape[1]}")
    print(f"[라벨 분포] " + ", ".join(f"{k} {v}" for k, v in dist.most_common()))
    print()

    m_raw = metrics("raw", raw, labels, known_mask, rng)
    m_cen = metrics("centered", cen, labels, known_mask, rng)

    # ── 표 ───────────────────────────────────────────────
    keys = ["global_mean_norm", "avg_pairwise_cos", "silhouette", f"knn_purity@{KNN_K}"]
    better_high = {"silhouette", f"knn_purity@{KNN_K}"}   # 높을수록 좋음
    # mean_norm, pairwise_cos 는 절댓값이 0에 가까울수록 좋음

    print(f"{'지표':<22}{'raw':>12}{'centered':>12}{'개선(delta)':>16}")
    print("-" * 62)
    for k in keys:
        rv, cv = m_raw[k], m_cen[k]
        if k in better_high:
            delta = cv - rv
            mark = "↑좋아짐" if delta > 0 else ("↓나빠짐" if delta < 0 else "=")
        else:  # 0에 가까울수록 좋음 → 절댓값 감소가 개선
            delta = abs(rv) - abs(cv)
            mark = "↑좋아짐" if delta > 0 else ("↓나빠짐" if delta < 0 else "=")
        print(f"{k:<22}{rv:>12.5f}{cv:>12.5f}{delta:>+12.5f}  {mark}")
    print("-" * 62)
    print(f"(참고) 등방성 기대 mean_norm ≈ {m_raw['isotropic_baseline']:.5f}")
    print()

    # ── 해석 가이드 ──────────────────────────────────────
    sil_gain = m_cen["silhouette"] - m_raw["silhouette"]
    knn_gain = m_cen[f"knn_purity@{KNN_K}"] - m_raw[f"knn_purity@{KNN_K}"]
    raw_aniso = m_raw["global_mean_norm"]
    print("해석:")
    if raw_aniso < m_raw["isotropic_baseline"] * 1.5:
        print(f"  - raw 쏠림이 거의 없음(mean_norm {raw_aniso:.4f} ≈ 등방성 기준). 센터링이 뺄 게 별로 없음.")
    else:
        print(f"  - raw 에 쏠림 존재(mean_norm {raw_aniso:.4f} > 등방성 기준). 센터링이 의미 있을 여지.")
    if sil_gain <= 0.005 and knn_gain <= 0.005:
        print(f"  - silhouette {sil_gain:+.4f}, knn {knn_gain:+.4f}: 센터링이 분리도를 사실상 못 높임 → raw 로 통일해도 무방.")
    else:
        print(f"  - silhouette {sil_gain:+.4f}, knn {knn_gain:+.4f}: 센터링이 분리도를 높임 → embedding 유지가 이득.")

    out = {"config": {"n": n, "n_known": n_known, "K": KNN_K},
           "raw": m_raw, "centered": m_cen,
           "delta": {"silhouette": round(sil_gain, 5),
                     f"knn_purity@{KNN_K}": round(knn_gain, 5)}}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {OUT_PATH}")


main()