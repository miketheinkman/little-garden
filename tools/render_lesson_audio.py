"""Run with Piper's Python. Install piper-tts[alignment], soundfile and dtaidistance in the build environment."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from itertools import accumulate
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory, NamedTemporaryFile

import numpy as np
from dtaidistance import dtw_ndim
from piper import PiperVoice, SynthesisConfig
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
PACE = 1.15
APPROVED = "Say “sun”. Which letter makes its first sound?"
# Spell letter names explicitly. In running speech, e.g. "A" may otherwise sound like an article.
LETTER_PHONES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", (
    "ˈeɪ", "bˈiː", "sˈiː", "dˈiː", "ˈiː", "ˈɛf", "dʒˈiː", "ˈeɪtʃ", "ˈaɪ",
    "dʒˈeɪ", "kˈeɪ", "ˈɛl", "ˈɛm", "ˈɛn", "ˈoʊ", "pˈiː", "kjˈuː", "ˈɑːɹ",
    "ˈɛs", "tˈiː", "jˈuː", "vˈiː", "dˈʌbəljuː", "ˈɛks", "wˈaɪ", "zˈiː"), strict=True))
TARGET = re.compile(r'“(?P<quoted>[a-z]+)[.!?]?”|'
                    r'(?:(?i:trace) (?:lowercase )?|to form |press |capital |Look for |[Ff]ind (?:the (?:number )?)?)'
                    r'(?P<key>[A-Za-z]|[0-9]+)\b|Use your (?P<side>left|right) hand')


@lru_cache(maxsize=1)
def aligned_voice(model):
    return PiperVoice.load(model, include_alignments=True)


def utterances(text, model, is_word):
    """Piper phonemizes the complete sentence, preserving surrounding words and punctuation."""
    match = TARGET.search(text)
    if not (is_word or match):
        return [(text, None)]
    voice = aligned_voice(model)
    if is_word:
        value, sentence = text, "Say zebra."
    else:
        value = match[match.lastgroup]
        start, end = match.span(match.lastgroup)
        sentence = text[:start] + "zebra" + text[end:]
    if not is_word and match.lastgroup == "key" and value.isalpha():
        target = LETTER_PHONES[value.upper()]
    else:
        target = "".join(voice.phonemize(value)[0]).strip(".!?")
    # The marker gives an exact phoneme index, even when the same sound appears twice.
    marker = re.compile(r"z[ˈˌ]?iː?bɹə")
    lines = []
    spans = 0
    for phonemes in voice.phonemize(sentence):
        spoken = "".join(phonemes)
        found = marker.search(spoken)
        span = None
        if found:
            start = found.start()
            spoken = spoken[:start] + target + spoken[found.end():]
            span = (start, start + len(target))
            spans += 1
        lines.append(("[[" + spoken + "]]", span))
    if spans != 1:
        raise ValueError(f"Cannot locate the target in {text!r}")
    return lines


def spectral_frames(audio, hop):
    # Log energy in speech-frequency bands lets us match consonants and vowels
    # between two takes, even where their volume or durations differ.
    size = 512
    windows = np.lib.stride_tricks.sliding_window_view(np.pad(audio, size//2), size)[::hop]
    power = abs(np.fft.rfft(windows * np.hanning(size))) ** 2
    bands = np.unique(np.geomspace(1, size//2, 32).astype(int))
    features = np.log1p(np.add.reduceat(power, bands, axis=1))
    return np.ascontiguousarray(features, dtype=np.float64)


def emphasize(pcm, rate, line, span, model, word_only):
    # Keep the natural timing of the CLI take. Map the reference phoneme boundaries
    # to the actual recording before applying the gain or extracting a word.
    config = SynthesisConfig(length_scale=PACE, noise_w_scale=0)
    chunk, = aligned_voice(model).synthesize(line, config, include_alignments=True)
    alignment = chunk.phoneme_alignments
    if not alignment:
        raise ValueError(f"Cannot align the recording for {line!r}")
    edges = list(accumulate((int(a.num_samples) for a in alignment), initial=0))
    begin, finish = span
    # Skip the alignment's opening sentence token.
    start, end = edges[begin + 1], edges[finish + 1]
    phonemes = "".join(a.phoneme for a in alignment)
    stress = phonemes.find("ˈ", begin + 1, finish + 1)
    vowel = edges[stress] if stress >= 0 else start
    hop = round(rate * .010)
    reference = spectral_frames(chunk.audio_float_array, hop)
    recorded = spectral_frames(pcm, hop)
    path = np.asarray(dtw_ndim.warping_path(reference, recorded, use_c=True))
    clock = np.unique(path[:, 0], return_index=True)[1]
    start, vowel, end = np.rint(np.interp([start, vowel, end], path[clock, 0]*hop,
                                          path[clock, 1]*hop)).astype(int)
    t = np.arange(start, end)
    attack = np.clip((t-vowel)/(rate*.025), 0, 1)
    release = np.clip((end-t)/(rate*.045), 0, 1)
    pcm[start:end] *= 1 + .20 * np.minimum(attack, release)
    if word_only:
        # Keep the consonant attack and release when extracting the contextual pronunciation.
        return pcm[max(0,start-round(.015*rate)):min(len(pcm),end+round(.055*rate))]
    n = min(start, len(pcm)-start, round(.003*rate))
    if n:
        pcm[start-n:start] *= np.linspace(1,0,n)
        pcm[start:start+n] *= np.linspace(0,1,n)
    return np.concatenate((pcm[:start], np.zeros(round(.055*rate)), pcm[start:]))


def render_batch(args):
    model, entries = args
    with TemporaryDirectory() as temporary:
        temp = Path(temporary)
        prompts = [utterances(text, model, "/words/" in path) for path,text in entries]
        script = [line for prompt in prompts for line,_ in prompt]
        # Batch mode keeps the local voice loaded and emits one timestamp-named WAV per line.
        subprocess.run([sys.executable, "-m", "piper", "-m", model, "--length-scale", str(PACE),
                        "-d", str(temp)], input="\n".join(script)+"\n",
                       text=True, check=True, stdout=subprocess.DEVNULL)
        files = sorted(temp.glob("*.wav"), key=lambda p: int(p.stem))
        if len(files) != len(script):
            raise RuntimeError("Piper returned an unexpected number of recordings.")
        files = iter(files)
        for (path,_), prompt in zip(entries, prompts, strict=True):
            pieces = []
            for line, span in prompt:
                pcm, rate = sf.read(next(files), dtype="float32")
                if span:
                    pcm = emphasize(pcm, rate, line, span, model, "/words/" in path)
                pieces.append(pcm)
            pcm = np.concatenate(pieces)
            pcm *= min(1, .94/max(.001, np.abs(pcm).max()))
            dest = STATIC / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=dest.parent, suffix=".ogg", delete=False) as out:
                pending = Path(out.name)
            try:
                sf.write(pending, pcm, rate, format="OGG", subtype="VORBIS")
                decoded, saved_rate = sf.read(pending, dtype="float32")
                if (saved_rate != rate or len(decoded) != len(pcm)
                        or not np.isfinite(decoded).all() or np.max(np.abs(decoded)) < .01):
                    raise ValueError(f"Invalid audio for {path}")
                pending.replace(dest)
            finally:
                pending.unlink(missing_ok=True)
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(Path.home()/"piper/en_US-lessac-medium.onnx"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    catalog = json.loads(subprocess.check_output([ROOT/".venv/bin/python", ROOT/"manage.py", "lesson_audio_catalog"]))
    todo = []
    for path, text in catalog.items():
        dest = STATIC / path
        if dest.exists():
            continue
        if text == APPROVED:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(STATIC/"phonics/first-sound-sun-practice-pace.ogg", dest)
        else:
            todo.append((path,text))
    print(f"Rendering {len(todo)} of {len(catalog)} clips", flush=True)
    batches = [(args.model, todo[i:i+24]) for i in range(0,len(todo),24)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for done in accumulate(pool.map(render_batch,batches)):
            print(f"{done}/{len(todo)}",flush=True)


if __name__ == "__main__":
    main()
