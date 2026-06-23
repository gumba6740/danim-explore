"""
클러스터 순도(purity) 진단 스크립트
====================================
목적: 코드북을 정식으로 굽기 전에, 지금 임베딩으로 k-means를 돌렸을 때
      각 칸(클러스터)이 한 주제로 깨끗하게 갈리는지 측정한다.

      칸 47번이 "카페 9 / 등산 1" 이면 깨끗(순도 0.9),
      "카페 3 / 등산 3 / 맛집 4" 면 뒤죽박죽(순도 0.4).
      칸 대부분이 한 주제로 쏠리면 임베딩 품질 OK → 바로 코드북 고정으로.
      뒤죽박죽이 많으면 → 텍스트 정제부터 손대야 함.

실행:
    python manage.py shell < purity_check.py

필요 패키지:
    pip install scikit-learn numpy
"""

import numpy as np
from collections import Counter
from sklearn.cluster import KMeans

# ── 프로젝트에 맞게 import 경로만 바꾸세요 ────────────────────────────
from apps.posts.models import PostEmbedding
# ────────────────────────────────────────────────────────────────────

# ── 손잡이 ───────────────────────────────────────────────────────────
K = 80                 # 칸 개수. 955개면 80이 출발점(칸당 ~12개). 읽기 힘들면 30으로 낮춰도 됨
USE_CENTERED = True    # True면 센터링된 embedding, False면 raw_embedding 사용
                       # 추천 점수 계산에서 쓰는 거랑 반드시 같은 걸로!
SHOW_CLUSTERS = True   # 각 칸 내용을 제목까지 찍어볼지 (눈 검사용)
SAMPLES_PER_CLUSTER = 6  # 칸마다 제목 몇 개 보여줄지
# ────────────────────────────────────────────────────────────────────

# ── 주제 라벨 정의 ───────────────────────────────────────────────────
# 게시글에 category/tag 컬럼이 있으면 label_of()를 그걸 쓰도록 바꾸는 게 정확함.
# 없으면 아래 제목 키워드 매칭으로 자동 라벨링. 본인 데이터에 맞게 키워드 추가/수정하세요.
TOPIC_KEYWORDS = {
    # 구체적/희귀한 주제를 위에 (먼저 매칭되도록)
    "스쿠버":   ["스쿠버", "수중", "물속", "다이빙", "스노클"],
    "템플":     ["템플스테이", "사찰", "불국사", "송광사", "절에서", "고요한"],
    "기차":     ["기차", "열차", "기차역", "철도"],
    "와인":     ["와인", "와이너리"],
    "쇼핑":     ["쇼핑", "면세점", "스타필드", "백화점", "아울렛"],
    "온천":     ["온천", "스파", "사우나", "찜질"],
    "전통":     ["한옥", "전통", "하회마을", "고궁", "민속"],
    "전시":     ["전시", "미술관", "갤러리", "박물관", "아트"],
    "사진":     ["새벽", "일출", "노을", "풍경 사진", "야경"],
    "자전거":   ["자전거", "사이클", "라이딩"],
    # 기존 주제
    "카페":     ["카페", "커피", "디저트", "베이커리", "브런치"],
    "맛집":     ["맛집", "식당", "국밥", "삼겹살", "흑돼지", "비빔밥", "먹거리", "음식"],
    "등산":     ["등산", "트레킹", "둘레길", "정상", "능선"],
    "바다":     ["바다", "해변", "해수욕", "해안", "해운대", "파도", "포구"],
    "캠핑":     ["캠핑", "글램핑", "텐트", "차박", "백패킹"],
    "호수":     ["호수", "저수지", "계곡"],
    "도심":     ["도심", "시내", "골목", "거리"],
}

def label_of(post):
    """게시글 하나의 주제 라벨을 정한다.
    ★ category/tag 컬럼이 있으면 여기를 그걸로 교체:
        return getattr(post, "category", "기타") or "기타"
    """
    title = (post.title or "")
    for label, kws in TOPIC_KEYWORDS.items():
        if any(kw in title for kw in kws):
            return label
    return "기타"
# ────────────────────────────────────────────────────────────────────


def normalize(mat):
    """각 벡터를 길이 1로. 정규화하면 유클리드 k-means가 코사인 클러스터링과 같아짐."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def main():
    field = "embedding" if USE_CENTERED else "raw_embedding"
    print(f"[설정] K={K}, 벡터={field}, 라벨=제목 키워드 매칭\n")

    # 1) 임베딩 로드
    rows = list(
        PostEmbedding.objects
        .filter(**{f"{field}__isnull": False})
        .select_related("post")
    )
    if not rows:
        print(f"!! {field} 가 채워진 게시글이 없습니다.")
        return

    vecs = np.array([r.__getattribute__(field) for r in rows], dtype="float64")
    posts = [r.post for r in rows]
    labels = [label_of(p) for p in posts]
    vecs = normalize(vecs)

    n = len(rows)
    k = min(K, n)  # 게시글보다 칸이 많을 수 없음
    print(f"[데이터] 게시글 {n}개, 차원 {vecs.shape[1]}")

    # 라벨 분포 먼저 (라벨링 자체가 멀쩡한지 확인)
    label_dist = Counter(labels)
    print(f"[전체 라벨 분포] " +
          ", ".join(f"{lab} {cnt}" for lab, cnt in label_dist.most_common()))
    etc = label_dist.get("기타", 0)
    if etc / n > 0.4:
        print(f"  ⚠ '기타'가 {etc}개({etc/n:.0%})로 많음 → 키워드를 보강하면 진단이 정확해져요.\n")
    else:
        print()

    # 2) k-means
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    assign = km.fit_predict(vecs)

    # 3) 칸별 순도 계산
    #    한 칸의 순도 = 그 칸에서 가장 많은 주제의 비율 ('기타'는 분모에서 제외)
    cluster_purities = []
    weighted_sum = 0.0
    weighted_total = 0
    cluster_view = []

    for c in range(k):
        idx = [i for i in range(n) if assign[i] == c]
        if not idx:
            continue
        cnt = Counter(labels[i] for i in idx)
        known = {lab: v for lab, v in cnt.items() if lab != "기타"}
        size = len(idx)

        if known:
            dominant, dom_cnt = max(known.items(), key=lambda x: x[1])
            known_total = sum(known.values())
            purity = dom_cnt / known_total
            cluster_purities.append(purity)
            weighted_sum += dom_cnt
            weighted_total += known_total
        else:
            dominant, purity = "기타", 0.0

        cluster_view.append((c, size, dominant, purity, cnt, idx))

    overall = (weighted_sum / weighted_total) if weighted_total else 0.0

    # 4) 칸 내용 출력 (순도 낮은 것부터 = 문제 칸 먼저 보이게)
    if SHOW_CLUSTERS:
        print("=" * 60)
        print("칸별 내용 (순도 낮은 순 — 위에 있을수록 뒤죽박죽)")
        print("=" * 60)
        for c, size, dom, purity, cnt, idx in sorted(cluster_view, key=lambda x: x[3]):
            mix = ", ".join(f"{lab} {v}" for lab, v in cnt.most_common())
            flag = "⚠" if purity < 0.6 else "✓"
            print(f"\n{flag} 칸 {c:>2} | {size}개 | 순도 {purity:.2f} | 대표:{dom}")
            print(f"    구성: {mix}")
            for i in idx[:SAMPLES_PER_CLUSTER]:
                print(f"      - [{labels[i]}] {posts[i].title}")
            if size > SAMPLES_PER_CLUSTER:
                print(f"      ... 외 {size - SAMPLES_PER_CLUSTER}개")

    # 5) 요약
    clean = sum(1 for p in cluster_purities if p >= 0.6)
    print("\n" + "=" * 60)
    print("요약")
    print("=" * 60)
    print(f"전체 가중 순도 : {overall:.3f}   (1.0에 가까울수록 임베딩이 주제를 잘 가름)")
    if cluster_purities:
        print(f"깨끗한 칸     : {clean}/{len(cluster_purities)}개 (순도 0.6 이상)")
    print()
    if overall >= 0.75:
        print("→ 임베딩 품질 좋음. 손볼 것 없이 코드북 고정으로 가도 됨.")
    elif overall >= 0.55:
        print("→ 쓸 만함. 위 ⚠ 칸들이 어떤 주제끼리 섞이는지 보고,")
        print("  그 주제 글들 텍스트만 살짝 정제하면 충분.")
    else:
        print("→ 칸이 많이 뒤죽박죽. 텍스트 정제(HTML/이모지/정형구 제거,")
        print("  제목 가중)부터 손댄 뒤 다시 측정 권장. (또는 라벨 키워드부터 점검)")

    # 6) JSON 저장
    import json
    out = {
        "config": {"K": k, "field": field, "n_posts": n},
        "overall_purity": round(overall, 4),
        "clean_clusters": clean,
        "total_clusters": len(cluster_purities),
        "label_distribution": dict(label_dist),
        "clusters": [],
    }
    for c, size, dom, purity, cnt, idx in sorted(cluster_view, key=lambda x: x[3]):
        out["clusters"].append({
            "cluster_id": int(c),
            "size": size,
            "dominant_label": dom,
            "purity": round(purity, 4),
            "composition": dict(cnt),
            "titles": [
                {"label": labels[i], "title": posts[i].title}
                for i in idx
            ],
        })
    path = "purity_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] {path} 에 결과 저장됨")


main()