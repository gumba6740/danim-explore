from apps.users.models import User


def run():
    user_count = User.objects.filter(email__startswith="demo").count()
    print(f"데모 유저 {user_count} 명")