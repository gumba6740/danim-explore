from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.comments.models import Comment
from apps.explore.services.taste import build_codeword_counts, personalization_alpha
from apps.interactions.models import PostLike, PostClick
from apps.users.models import UserTaste

User = get_user_model()

CODEBOOK_VERSION = "v1"   # 현재 게시글 codewords 가 박힌 코드북 버전과 일치시킬 것


def _get_active_users():
    """모든 유저를 가져오지 않고, 7일 이내에 활동한 적이 있는 유저만 골라서 가져오는 함수"""
    cutoff = timezone.now() - timedelta(days=7)
    user_ids = set()
    # 7일 동안 3개의 상호작용 중 하나라도 했으면 그 유저는 활동 유저로 간주
    for model in (PostLike, Comment, PostClick):
        ids = (model.objects.filter(created_at__gte=cutoff)
               .values_list("user_id", flat=True))
        user_ids.update(ids)
    return User.objects.filter(id__in=user_ids)


class Command(BaseCommand):
    """
    crontab으로 매일 새벽에 돌릴 커맨드.
    UserTaste에 코드워드 카운트와 알파값 저장 및 PostClick의 데이터를 최근 7일 전후 것만 남김.
    """

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=7)

        count = 0
        for user in _get_active_users():  # 활동 유저 반환
            counts = build_codeword_counts(user, version=CODEBOOK_VERSION)  # 코드워드 카운트 맵
            if counts:
                alpha = personalization_alpha(user)  # 개인화 알파 반환
                UserTaste.objects.update_or_create(
                    user=user,
                    defaults={
                        "codeword_counts": counts,
                        "codebook_version": CODEBOOK_VERSION,
                        "alpha": alpha,
                    },
                )
                count += 1

        # PostClick의 데이터를 7일 전후로 유지
        deleted, _ = PostClick.objects.filter(created_at__lt=cutoff).delete()

        # 6개월 이상 갱신 안 된 취향 삭제.
        # 7일간 활동 안함 -> 알파 및 취향값 그대로 유지(7일 내에 활동한 유저만 계산하니까)
        # -> 7일 ~ 6개월 내에 다시 활동하면 시간감쇠를 포함해 재계산
        # -> 6개월 이후에 활동하면, 취향이 삭제됐으므로 cold starter로 간주
        # -> 하루 지나고 재계산
        taste_cutoff = timezone.now() - timedelta(days=180)
        taste_deleted, _ = UserTaste.objects.filter(
            updated_at__lt=taste_cutoff
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"취향 {count}명 갱신, "
                f"오래된 클릭 {deleted}건, stale 취향 {taste_deleted}건 삭제"
            )
        )