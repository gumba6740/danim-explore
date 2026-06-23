import string
from datetime import date
from apps.users.models import User

base = string.ascii_lowercase

def make_email_and_name():
    last_user = (
        User.objects.filter(email__startswith="demo")
        .order_by("-email")
        .first()
    )
    if last_user is None:
        index = -1
    else:
        index = int(base.index(last_user.email[4]))
    if index == 25:
        raise ValueError("zzzzzzzz")

    email = f"demo{base[index+1]}@demo.com"
    name = base[index+1]

    return email, name


def run(num):
    for _ in range(int(num)):
        email, name = make_email_and_name()
        birthdate = date(1111,11,11)
        User.objects.create(
            email=email,
            password="password1234",
            nickname=name,
            name=name,
            birth_day=birthdate,
            is_active=True,
            is_email_verified=True,
        )

    print("=="*20)
    print(f"{num} 유저 생성 성공")
    print("=="*20)