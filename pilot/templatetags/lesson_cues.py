"""Action cues follow the lesson skill, independently of the correct answer."""
import re

from django import template

from pilot.explorations import EXTRA_OUTLINES

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
    "🔦": "shadow light-paths",
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
    "🚂": "train-tracks", "🌉": "bridges", "📦": "delivery-routes", "⚙️": "gears-motion", "🔐": "gates-switches",
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
    "The bench":"🪑", "The hive":"🍯", "The lamp":"💡", "The nest":"🪺", "The log":"🪵", "The pot":"🪴",
    "To keep the parcel safe":"📦", "To take a nap":"💤", "To catch the wind":"🌬️",
    "A ribbon":"🎀", "A map":"🗺️", "A card":"💌", "A drawing":"🖼️", "A seed packet":"🌱",
    "The red cab":"🚚", "The big rig":"🚛", "The tool box":"🧰", "The road map":"🗺️",
    "The moon map":"🌕🗺️", "The red sun":"☀️", "The jet pod":"🚀", "The star lab":"🔭",
    "The sea bed":"🪸", "The fin tip":"🦈", "The red fin":"🐟", "The wet net":"🥅",
    "The rail map":"🗺️", "The box car":"🚃", "The new cap":"🧢", "The oak log":"🪵",
    "The red fox":"🦊", "The nut bag":"🥜", "The sun hat":"👒", "The hot bun":"🥖",
    "The jam pot":"🫙", "The egg cup":"🥚", "The nut bar":"🥜", "The dig pit":"⛏️",
    "The mud map":"🗺️", "The egg bed":"🪺", "The sun cap":"🧢", "The hay bed":"🌾",
    "The pig pen":"🐖", "The red hen":"🐔", "The mud pit":"🟤", "The bee hut":"🐝",
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

@register.filter
def basket_labels(item):
    """Use a category exemplar even on rounds saved before the visual hints."""
    result = []
    for index, label in enumerate(item["bins"], 1):
        if isinstance(label, dict):
            result.append(label)
        else:
            example = next(piece["icon"] for piece in item["pieces"] if piece["bin"] == index)
            result.append({"label": label, "example": example})
    return result


@register.filter
def bundle_groups(display):
    # Saved prompts describe the starting configuration, including unbundling tasks.
    counts = re.findall(r"\d+", display)
    if len(counts) == 2:
        return {"bags": range(int(counts[0])), "loose": range(int(counts[1]))}

@register.filter
def trail_dots(item):
    nodes = item["dots"]
    # Saved envelopes used to start across the top. Keep their labels and handedness.
    if item["outline"] == "envelope" and nodes[0]["y"] == nodes[1]["y"]:
        mirrored = nodes[0]["x"] > nodes[1]["x"]
        return [dict(node, x=100-x if mirrored else x, y=y)
                for node, (x, y) in zip(nodes, EXTRA_OUTLINES["envelope"])]
    return nodes
