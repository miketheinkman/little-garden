## Feature verification

For each feature, run the Django suite and the headless Playwright workflow documented under “Visual review” in README.md. Extend qa/visual.py with the affected page, a representative interaction and its resulting state when existing coverage misses the change. Include relevant empty, filled, validation or error states. Use the disposable test household.

Inspect the actual screenshots at desktop and phone sizes in light and dark themes. Check text contrast, control labels and focus, card spacing and alignment, overflow, and the primary action. Fix observed issues and rerun the checks. Report which feature flow was exercised and any unverified behavior.

## Lesson audio

For new playable words and recorded directions, use Piper with the `en_US-lessac-medium` voice. On the pilot host, run `/home/mike/piper/.venv/bin/python -m piper -m /home/mike/piper/en_US-lessac-medium.onnx`. Use length scale 1.15 and preserve the approved in-sentence emphasis on phonics targets. The batch builder renders temporary WAVs and encodes Ogg Vorbis with libsndfile.

Run `/home/mike/piper/.venv/bin/python tools/render_lesson_audio.py` after curriculum edits. Its build-only dependencies are `piper-tts[alignment]`, `soundfile`, and `dtaidistance`. The generator reuses existing recordings and enumerates the same lessons, variations, and themes as the player. Run `.venv/bin/python manage.py lesson_audio_catalog --check` to verify coverage.

## Family lesson feedback

When a change comes from lesson feedback, verify it in the affected lesson and make it available on the pilot before replying on the original entry. Say what changed and how the family can try it. If part of a request is still open, name that part in the reply. Use the dashboard reply flow so the family’s email preference is respected. Check the existing replies before posting another update. Mark the entry resolved after the fix and its reply are live. Leave partial fixes open. Read the family’s latest follow-up when a thread reopens.

## Public family guides

In every curriculum-related commit, review the public Curriculum page against the actual catalog, placement rules and learner experience. The subject list uses the current catalog directly. Update the explanations and recapture affected lesson images in the same commit. Use only the disposable QA household. Run `UPDATE_GUIDE_SCREENSHOTS=1 .venv/bin/python manage.py test qa.visual.VisualReview.test_curriculum_gallery` to refresh the three published lesson screenshots, then inspect the crops.

For each change to a parent or learner feature, walk the affected task in the public How it works guide. Update its directions, labels and topic navigation in the same commit when the workflow changes. The feature pipeline exercises public navigation, curriculum examples, sharing and the invite request flow on desktop and phone in both themes.
