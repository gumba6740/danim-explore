"""
DB의 유저 + Location을 읽어 Groq로 게시글을 생성하고 posts.json 에 저장.

배치 위치: apps/posts/management/commands/generate_posts.py

사용 전:
  uv add --dev groq
  export GROQ_API_KEY="발급받은_키"

실행:
  python manage.py generate_posts
  python manage.py generate_posts --target 200
"""

import json
import os
import random
import time
from collections import deque
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from groq import Groq

from apps.posts.models import Location  # 경로가 다르면 수정

User = get_user_model()

MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
RPM_PER_MODEL = 28


class RateLimiter:
    def __init__(self, rpm):
        self.rpm = rpm
        self.calls = {}

    def wait(self, model):
        now = time.monotonic()
        q = self.calls.setdefault(model, deque())
        while q and now - q[0] >= 60:
            q.popleft()
        if len(q) >= self.rpm:
            time.sleep(max(60 - (now - q[0]) + 0.1, 0))
            return self.wait(model)
        q.append(time.monotonic())


def calc_age(birth_day: date) -> int:
    today = date.today()
    return (
        today.year
        - birth_day.year
        - ((today.month, today.day) < (birth_day.month, birth_day.day))
    )


def build_prompt(persona, age, length_hint, spots):
    # spots: 글 순서대로 배정된 장소 리스트 (글 개수 = len(spots))
    n = len(spots)
    assignments = "\n".join(f"  {i + 1}번 글: {s}" for i, s in enumerate(spots))
    return f"""너는 국내 여행 SNS에 피드 글을 올리는 한국인 유저야. 아래 유저로 빙의해서 게시글 {n}개를 작성해.

[유저 정보]
- 나이: {age}세
- 여행 페르소나: {persona}

[글별 여행지 지정]
- 각 글은 아래에 지정된 '한 곳'에 대해서만 작성해. 지정된 지역 외 다른 지역(특히 해외)은 절대 언급하지 마.
{assignments}

[작성 조건]
1. 인스타그램/스레드(Threads) 감성으로 자연스럽게.
2. 반드시 한국어로 작성. (해시태그도 한국어 위주)
3. 말투와 관심사는 나이와 페르소나에 어울리게.
4. 각 글에 관련 해시태그 3~5개 포함.
5. 본문 길이는 '{length_hint}'.
7. 글의 내용은 반드시 지정된 그 지역에 대한 것이어야 해.

[출력 형식]
- 설명·머리말 없이 JSON 배열만 출력해. 배열 길이는 정확히 {n}개.
- 배열은 위 1번~{n}번 순서와 동일하게.
- 각 원소는 {{"title": "...", "content": "..."}} 형태의 객체.
- title: 게시글 제목 (20자 내외, 최대 100자).
- content: 본문 + 해시태그.
- 예시: [{{"title": "경주 한옥 카페", "content": "오늘 다녀온 곳... #경주카페"}}]"""


def parse_posts(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    data = json.loads(text)

    posts = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()[:100]
        content = str(item.get("content", "")).strip()
        if title and content:
            posts.append({"title": title, "content": content})
    return posts


class Command(BaseCommand):
    help = "Groq로 게시글을 생성해 posts.json에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--target", type=int, default=1000)
        parser.add_argument("--per-request", type=int, default=5)
        parser.add_argument("--output", default="posts3.json")

    def handle(self, *args, **options):
        if not os.environ.get("GROQ_API_KEY"):
            raise CommandError("환경변수 GROQ_API_KEY 가 필요합니다.")

        target = options["target"]
        per_request = options["per_request"]
        output = options["output"]

        users = [u for u in User.objects.all() if u.intro]
        if not users:
            raise CommandError("intro가 채워진 유저가 없습니다. 먼저 seed_users를 실행하세요.")

        # 시 단위만 쓰려면 .filter(level=3), 전부 쓰려면 그대로
        locations = list(Location.objects.values_list("place_name", flat=True))
        if not locations:
            raise CommandError("Location 데이터가 없습니다.")

        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        limiter = RateLimiter(RPM_PER_MODEL)
        length_hints = ["짧게 2~3줄", "중간 4~5줄", "길게 6~8줄"]

        if os.path.exists(output):
            with open(output, encoding="utf-8") as f:
                posts = json.load(f)
        else:
            posts = []
        i = 0
        while len(posts) < target:
            user = users[i % len(users)]
            model = MODELS[i % len(MODELS)]
            length_hint = length_hints[i % len(length_hints)]
            i += 1

            # 글마다 장소 1곳씩 배정 (중복 허용해서 후보가 적어도 동작)
            spots = [random.choice(locations) for _ in range(per_request)]

            persona = user.intro
            age = calc_age(user.birth_day)
            prompt = build_prompt(persona, age, length_hint, spots)

            batch = []
            for attempt in range(4):
                try:
                    limiter.wait(model)
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=1.0,
                        max_completion_tokens=4000,
                    )
                    batch = parse_posts(resp.choices[0].message.content)
                    break
                except Exception as e:
                    wait = 2**attempt
                    self.stdout.write(f"  재시도 {attempt + 1}/4 ({model}): {e} → {wait}s")
                    time.sleep(wait)

            # 응답 순서 = 장소 순서. 짝이 맞는 만큼만 저장.
            for idx, p in enumerate(batch):
                if idx >= len(spots):
                    break
                posts.append(
                    {
                        "email": user.email,
                        "location": spots[idx],  # place_name
                        "title": p["title"],
                        "content": p["content"],
                    }
                )

            with open(output, "w", encoding="utf-8") as f:
                json.dump(posts, f, ensure_ascii=False, indent=2)

            self.stdout.write(f"진행: {len(posts)}/{target}  (요청 {i}회, {model})")

        posts = posts[:target]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)

        self.stdout.write(
            self.style.SUCCESS(f"완료! {len(posts)}개를 {output}에 저장했습니다.")
        )