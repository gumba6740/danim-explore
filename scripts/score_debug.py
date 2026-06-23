import math
from django.utils import timezone

from apps.explore.services import order_prod as O
from apps.explore.services.feed_prod import TasteProfile
from apps.posts.models import Post
from apps.users.models import UserTaste
from django.contrib.auth import get_user_model

User = get_user_model()
now = timezone.now().replace(minute=0, second=0, microsecond=0)


def _base(age_days, post):
    if age_days < 7:
        return O._rookie_score(post)
    if age_days < 30:
        return O._main_score(post, now)
    return O._sub_score(post, now)


def run(user_name, keyword):
    u = User.objects.get(name=user_name)
    taste = UserTaste.objects.filter(user=u).first()
    profile = TasteProfile.from_taste(taste)

    rows = []
    for post in Post.objects.filter(title__icontains=keyword).select_related("vector"):
        age = O._age_days(post, now)
        decay = O._sigmoid_decay(age)
        base = _base(age, post)
        cos = O._post_affinity(post, profile)
        if cos <= 0.0:
            boost, final = 1.0, base
        else:
            boost = math.exp(O.PERSONALIZATION_BETA * cos) ** profile.alpha
            final = base * boost
        rows.append((final, age, decay, base, cos, boost, post.title[:30]))

    rows.sort(reverse=True)
    print(f"\n[{keyword}] user={user_name} alpha={profile.alpha} norm={profile.norm:.3f}")
    print(f"{'final':>9} {'age':>5} {'decay':>6} {'base':>8} {'cos':>5} {'boost':>7}  title")
    for final, age, decay, base, cos, boost, title in rows:
        print(f"{final:>9.3f} {age:>5.1f} {decay:>6.3f} {base:>8.3f} {cos:>5.2f} {boost:>7.2f}  {title}")