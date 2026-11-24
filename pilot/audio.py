"""Stable asset names for the text displayed in a saved or generated lesson round."""
from hashlib import sha256
import re


def clip_path(kind, text):
    digest = sha256(text.encode("utf-8")).hexdigest()[:24]
    if kind == "word":
        name = text if re.fullmatch(r"[a-z]+", text) else digest
        return f"phonics/words/{name}.ogg"
    return f"phonics/directions/{digest[:2]}/{digest}.ogg"


def spoken_directions(key, item):
    if key == "snail-v1" and item.get("display"):
        return f'{item["display"]} {item["prompt"]}'
    return item["prompt"]


def lesson_clips(item, key=None):
    return {"direction_clip": clip_path("directions", spoken_directions(key, item)),
            "word_clip": clip_path("word", item["word"]) if item.get("word") else None}
