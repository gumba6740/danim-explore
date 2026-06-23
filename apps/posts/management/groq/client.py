"""
Groq로 여행 SNS 게시글 1000개를 생성해서 JSON 파일에 저장하는 스크립트.

사용 전:
  pip install groq
  export GROQ_API_KEY="발급받은_키"

실행:
  python generate_posts.py
"""

import json
import os
import random
import time
from collections import deque

from groq import Groq


client = Groq(api_key=os.environ.get("GROQ_KEY"))

# ── 설정 ─────────────────────────────────────────────
# rpm 30 / rpd 1000 짜리 모델 2개. 본인이 쓰는 모델명으로 교체하세요.
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

TARGET_POSTS = 1000          # 최종 목표 게시글 수
POSTS_PER_REQUEST = 5        # 한 요청에서 뽑을 게시글 수
RPM_PER_MODEL = 28           # 모델당 분당 요청 수 (30보다 살짝 낮게)
OUTPUT_FILE = "posts.json"

# 성별 제거 버전 페르소나
user_features_data = [
    {"age": 24, "persona": "프로 배낭러"},
    {"age": 21, "persona": "프로 뚜벅이"},
    {"age": 34, "persona": "호캉스 마스터"},
    {"age": 29, "persona": "전국 맛집 헌터"},
    {"age": 27, "persona": "감성 카페 투어러"},
    {"age": 38, "persona": "주말 캠핑 러버"},
    {"age": 23, "persona": "사진 한 장에 진심인 인생샷러"},
    {"age": 31, "persona": "혼행 마니아"},
    {"age": 26, "persona": "가성비 여행 끝판왕"},
    {"age": 45, "persona": "럭셔리 트래블러"},
    {"age": 22, "persona": "액티비티 중독자"},
    {"age": 36, "persona": "역사 유적 탐방러"},
    {"age": 41, "persona": "미식 여행가"},
    {"age": 33, "persona": "워케이션 디지털 노마드"},
    {"age": 39, "persona": "아이 둘 데리고 다니는 가족 여행 플래너"},
    {"age": 28, "persona": "캠핑카 유목민"},
    {"age": 30, "persona": "주말마다 산 타는 등산 마니아"},
    {"age": 25, "persona": "서핑하러 바다만 찾아다니는 바다 러버"},
    {"age": 35, "persona": "야경 명소 헌터"},
    {"age": 52, "persona": "전통시장 골목 탐험가"},
    {"age": 48, "persona": "온천·스파 힐링러"},
    {"age": 23, "persona": "음악 페스티벌 추적자"},
    {"age": 32, "persona": "미술관·전시 순례자"},
    {"age": 27, "persona": "로컬 체험 덕후"},
    {"age": 29, "persona": "자전거로 국토종주하는 라이더"},
    {"age": 44, "persona": "기차 여행 낭만파"},
    {"age": 24, "persona": "겨울만 기다리는 스키·보드 매니아"},
    {"age": 37, "persona": "스쿠버 다이빙 애호가"},
    {"age": 55, "persona": "사찰·템플스테이 순례자"},
    {"age": 42, "persona": "와이너리 투어러"},
    {"age": 28, "persona": "별 보러 다니는 천문 덕후"},
    {"age": 26, "persona": "폐역·이색 명소 탐험가"},
    {"age": 33, "persona": "반려견 동반 여행러"},
    {"age": 30, "persona": "미니멀 초경량 백패커"},
    {"age": 46, "persona": "면세점 쇼핑이 여행의 절반인 쇼핑러"},
    {"age": 58, "persona": "주말 골프 여행족"},
    {"age": 60, "persona": "크루즈 여행 즐기는 시니어 트래블러"},
    {"age": 34, "persona": "당일치기 드라이브 코스 마스터"},
    {"age": 25, "persona": "디저트 카페만 골라 다니는 빵지순례러"},
    {"age": 40, "persona": "캠퍼밴 끌고 다니는 차박 부부"},
]


# ── 모델별 rate limiter ──────────────────────────────
class RateLimiter:
    """모델별로 최근 호출 시각을 추적해 분당 제한을 넘지 않게 대기시킨다."""

    def __init__(self, rpm):
        self.rpm = rpm
        self.calls = {}  # model -> deque of timestamps

    def wait(self, model):
        now = time.monotonic()
        q = self.calls.setdefault(model, deque())
        # 60초보다 오래된 기록 제거
        while q and now - q[0] >= 60:
            q.popleft()
        if len(q) >= self.rpm:
            sleep_for = 60 - (now - q[0]) + 0.1
            time.sleep(max(sleep_for, 0))
            return self.wait(model)
        q.append(time.monotonic())


limiter = RateLimiter(RPM_PER_MODEL)


# ── 프롬프트 ─────────────────────────────────────────
def build_prompt(persona, age, n):
    length_hint = random.choice(
        ["짧게 2~3줄", "중간 4~5줄", "길게 6~8줄"]
    )
    return f"""너는 여행 SNS에 피드 글을 올리는 유저야. 아래 유저로 빙의해서 서로 다른 SNS 게시글 {n}개를 작성해.

[유저 정보]
- 나이: {age}세
- 여행 페르소나: {persona}

[작성 조건]
1. 인스타그램/스레드(Threads) 감성으로 자연스럽게.
2. 말투와 관심사는 나이와 페르소나에 어울리게.
3. 각 글에 관련 해시태그 3~5개 포함.
4. 글 길이는 '{length_hint}'.
5. {n}개의 글은 서로 소재가 겹치지 않게 다양하게.

[출력 형식]
- 설명·머리말 없이 JSON 배열만 출력해.
- 배열의 각 원소는 게시글 본문(해시태그 포함) 문자열 1개.
- 예시: ["첫 번째 게시글...", "두 번째 게시글..."]"""


def parse_posts(raw):
    """모델 응답에서 JSON 배열을 최대한 안전하게 뽑아낸다."""
    text = raw.strip()
    # 코드펜스 제거
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # 배열 부분만 잘라내기
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    data = json.loads(text)
    return [str(item).strip() for item in data if str(item).strip()]


def request_batch(model, persona, age, n, max_retries=4):
    prompt = build_prompt(persona, age, n)
    for attempt in range(max_retries):
        try:
            limiter.wait(model)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,  # 다양성 위해 높게
            )
            return parse_posts(resp.choices[0].message.content)
        except Exception as e:
            wait = 2 ** attempt  # 1, 2, 4, 8초 백오프
            print(f"  [재시도 {attempt + 1}/{max_retries}] {model}: {e} → {wait}s 대기")
            time.sleep(wait)
    print(f"  [실패] {model} / {persona} 배치 포기")
    return []


def save(posts):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


# ── 메인 ─────────────────────────────────────────────
def main():
    posts = []
    i = 0
    while len(posts) < TARGET_POSTS:
        user = user_features_data[i % len(user_features_data)]
        model = MODELS[i % len(MODELS)]
        i += 1

        contents = request_batch(
            model, user["persona"], user["age"], POSTS_PER_REQUEST
        )
        for c in contents:
            posts.append(
                {
                    "persona": user["persona"],
                    "age": user["age"],
                    "content": c,
                }
            )

        save(posts)  # 배치마다 중간 저장
        print(f"진행: {len(posts)}/{TARGET_POSTS}  (요청 {i}회, 모델 {model})")

    # 목표 초과분 잘라내기
    posts = posts[:TARGET_POSTS]
    save(posts)
    print(f"\n완료! {len(posts)}개 게시글을 {OUTPUT_FILE}에 저장했습니다.")


if __name__ == "__main__":
    main()