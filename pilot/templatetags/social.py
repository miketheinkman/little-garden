from urllib.parse import urlencode

from django import template

register = template.Library()
WELCOME = "https://littlegarden.academy/"
MESSAGE = "Little Garden · Free homeschool lessons for families"
POST = f"{MESSAGE} {WELCOME}"


def compose(base, **fields):
    return f"{base}?{urlencode(fields)}"


# Keep the shared address independent of the visitor's current page and account.
DESTINATIONS = (
    ("Facebook", "facebook-f", compose("https://www.facebook.com/sharer/sharer.php", u=WELCOME)),
    ("Instagram", "instagram", "#share-instagram"),
    ("TikTok", "tiktok", "#share-tiktok"),
    ("X", "x-twitter", compose("https://twitter.com/intent/tweet", url=WELCOME, text=MESSAGE)),
    ("YouTube", "youtube", "#share-youtube"),
    ("Threads", "threads", compose("https://www.threads.com/intent/post", text=POST)),
    ("WhatsApp", "whatsapp", compose("https://wa.me/", text=POST)),
    ("Pinterest", "pinterest-p", compose("https://www.pinterest.com/pin/create/button/", url=WELCOME,
                                         media=WELCOME + "static/brand/icon-512.png", description=MESSAGE)),
    ("Reddit", "reddit-alien", compose("https://www.reddit.com/submit", url=WELCOME, title=MESSAGE)),
    ("LinkedIn", "linkedin-in", compose("https://www.linkedin.com/sharing/share-offsite/", url=WELCOME)),
    ("Bluesky", "bluesky", compose("https://bsky.app/intent/compose", text=POST)),
    ("Telegram", "telegram", compose("https://t.me/share/url", url=WELCOME, text=MESSAGE)),
)

MANUAL = (
    ("Instagram", "instagram", "Paste the link into a message or add a link sticker to your Story.",
     "https://www.instagram.com/"),
    ("TikTok", "tiktok", "Paste the link into a message to someone you want to share Little Garden with.",
     "https://www.tiktok.com/"),
    ("YouTube", "youtube", "Paste the link into a post on your channel.",
     "https://www.youtube.com/"),
)


@register.inclusion_tag("share_links.html")
def share_links():
    return {"destinations": DESTINATIONS, "manual": MANUAL, "welcome": WELCOME}
