"""Action cues follow the lesson skill, independently of the correct answer."""
from django import template

register = template.Library()

ACTION_GROUPS = {
    "🎧": "sounds middle-sound digraphs blend sound-check rhymes sound-memory hear-number animal-calls",
    "⌨️": "keys number-keys case-match signs key-check shift backspace my-letters",
    "✍️": "lines letters lowercase digits river",
    "📖": "book snail story sentence",
    "🖱️": "ladybugs",
    "🧺": "berry-basket market sort-baskets color-baskets",
    "🔢": "count1 count2 five ten tens number-check more twos",
    "🧩": "pattern same-different alphabet-gap",
    "👏": "drums",
    "🥁": "syllables",
    "🫘": "beans",
    "🥕": "harvest",
    "✂️": "scissors",
    "🔦": "shadow",
    "🌤️": "weather",
    "🎨": "color draw match-paint name-paint mix-paint",
    "🪞": "mirror",
    "🧭": "arrow-maze left-right left-right-pics over-under inside-outside",
    "🪄": "magic-e",
    "📏": "measure big-small tall-short",
    "🪙": "coins money-id money-total",
    "🕒": "clock",
    "💧": "water-works sink-float",
    "🌿": "living",
    "🚂": "train-tracks",
    "🃏": "letter-memory picture-memory",
    "⚖️": "seesaw",
    "🐾": "animal-lookout animal-words",
    "🗓️": "holiday-clues holiday-traditions",
    "✏️": "number-dots letter-dots",
    "➕": "add-groups",
    "➖": "take-away",
    "💭": "real-imaginary",
}
ACTION_ICONS = {slug: icon for icon, slugs in ACTION_GROUPS.items() for slug in slugs.split()}


@register.filter
def prompt_icon(key):
    return ACTION_ICONS.get(str(key).rsplit("-v", 1)[0], "👆")


# Picture labels for choices that ask a child to recognize an idea rather than decode text.
STORY_ICONS = {
    "The gate":"🚪", "The door":"🚪", "The red pot":"🪴", "The pond":"💧", "At the pond":"💧",
    "To find Dot":"🔎", "To eat":"🍽️", "To stay dry":"☂️", "It rained":"🌧️",
    "Dot opened it":"📬", "Pip rested":"💤", "Bee":"🐝", "Moth":"🦋", "Pip":"🐌",
    "To eat lunch":"🍽️", "To hold the seeds":"🌱", "To hide":"🫣", "A moth flew":"🦋",
    "Pip waved":"👋", "Seeds fell into her cup":"🌱", "Inside the log":"🪵", "In a nest":"🪺",
    "To find a log":"🪵", "To cross the water":"🌉", "To dry off":"☀️", "He displayed it":"🖼️",
    "It was wet":"💧", "Duck swam away":"🦆", "Pip’s home":"🏠", "To keep it dry":"☂️",
    "To hide it from a friend":"🫣", "To carry more":"📦", "Kit lifts the lid":"📬",
    "Pip walks away":"👣", "Rain falls":"🌧️",
}


@register.simple_tag
def choice_icon(key, lesson, choice):
    if lesson["kind"] == "adult":
        return "✓"
    if str(key).startswith("snail-v"):
        return STORY_ICONS.get(choice, "📍")
    return ""
