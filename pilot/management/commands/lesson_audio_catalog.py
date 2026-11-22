import json

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from pilot.audio import clip_path
from pilot.practice import LESSONS, build_round, round_count
from pilot.themes import THEMES, themed_round


class Command(BaseCommand):
    help = "List every distinct curriculum recording, including legacy rounds and themes."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Check that every expected recording is present.")

    def handle(self, *args, **options):
        directions, words = set(), set()
        for key in LESSONS:
            for variation in range(round_count(key)):
                base = build_round(key, variation)
                for theme in THEMES:
                    for item in themed_round(key, base, theme, variation)["items"]:
                        directions.add(item["prompt"])
                        if item.get("word"):
                            words.add(item["word"])
        catalog = {clip_path(kind, text): text for kind, texts in (("directions", directions), ("word", words))
                   for text in texts}
        if len(catalog) != len(directions) + len(words):
            raise CommandError("Two different recordings share a path.")
        if options["check"]:
            missing = [path for path in catalog if not (settings.BASE_DIR / "static" / path).is_file()]
            if missing:
                raise CommandError(f"{len(missing)} clips missing, including {missing[0]}")
            return f"{len(directions)} directions and {len(words)} words present."
        return json.dumps(catalog, sort_keys=True, ensure_ascii=False)
