"""Stable asset names for the text displayed in a saved or generated lesson round."""
from hashlib import sha256
import re


def clip_path(kind, text):
    digest = sha256(text.encode("utf-8")).hexdigest()[:24]
    if kind == "word":
        name = text if re.fullmatch(r"[a-z]+", text) else digest
        return f"phonics/words/{name}.ogg"
    return f"phonics/directions/{digest[:2]}/{digest}.ogg"


def lesson_clips(item):
    return {"direction_clip": clip_path("directions", item["prompt"]),
            "word_clip": clip_path("word", item["word"]) if item.get("word") else None}
