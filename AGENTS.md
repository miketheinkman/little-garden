## Feature verification

For each feature, run the Django suite and the headless Playwright workflow documented under “Visual review” in README.md. Extend qa/visual.py with the affected page, a representative interaction and its resulting state when existing coverage misses the change. Include relevant empty, filled, validation or error states. Use the disposable test household.

Inspect the actual screenshots at desktop and phone sizes in light and dark themes. Check text contrast, control labels and focus, card spacing and alignment, overflow, and the primary action. Fix observed issues and rerun the checks. Report which feature flow was exercised and any unverified behavior.

## Lesson audio

For new playable words and recorded directions, use Piper with the `en_US-lessac-medium` voice. On the pilot host, run `/home/mike/piper/.venv/bin/python -m piper -m /home/mike/piper/en_US-lessac-medium.onnx`. Use length scale 1.15 and preserve the approved in-sentence emphasis on phonics targets. The batch builder renders temporary WAVs and encodes Ogg Vorbis with libsndfile.

Run `/home/mike/piper/.venv/bin/python tools/render_lesson_audio.py` after curriculum edits. Its build-only dependencies are `piper-tts[alignment]`, `soundfile`, and `dtaidistance`. The generator reuses existing recordings and enumerates the same lessons, variations, and themes as the player. Run `.venv/bin/python manage.py lesson_audio_catalog --check` to verify coverage.
