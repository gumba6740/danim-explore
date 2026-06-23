import sys
from apps.users.models import User


def run():
    target_users = User.objects.filter(email__startswith="demo")
    count = target_users.count()
    if count == 0:
        print("삭제할 demo 유저가 존재하지 않습니다.")
        return

    print("=" * 50)
    print(f"demo 유저 데이터 {count}개")
    print("=" * 50)

    user_input = input("정말로 삭제하시겠습니까? y: ")

    if user_input.strip().lower() == 'y':
        deleted_count, _ = target_users.delete()
        print(f" 성공적으로 {deleted_count}개의 유저 데이터를 삭제했습니다.")
    else:
        print("취소")
        sys.exit(0)
