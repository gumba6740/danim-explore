import random
from apps.posts.management.persona import user_persona

post_length = random.choice(["간결한 글 (2~3줄)", "중간 길이 글 (4~5줄)", "긴 글 (6~8줄)"])

# 2. 리스트에서 무작위로 유저 1명 선택
selected_user = random.choice(user_persona)

# 3. 고정된 프롬프트 템플릿에 선택된 유저 정보 주입 (F-string 활용)
base_prompt = f"""
너는 지금부터 여행 SNS에 피드 글을 올리는 유저야. 아래의 유저 정보를 바탕으로 빙의해서 실감 나는 SNS 게시글 1개를 작성해 줘.

[유저 정보]
- 나이: {selected_user['age']}세
- 여행 페르소나: {selected_user['persona']}

[작성 조건]
1. 인스타그램이나 스레드(Threads) 감성으로 자연스럽게 작성해 줘.
2. 말투와 관심사는 나이와 성별, 페르소나에 완벽히 어울려야 해.
3. 관련 해시태그를 3~5개 포함해 줘.
4. 글의 길이는 '{post_length}'로 작성해줘.
"""
