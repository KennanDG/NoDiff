"""Casual-speech helper for the voice agent.

Produces short, natural-sounding spoken phrases for everyday conversational
situations (greeting, acknowledging, thinking out loud, agreeing, apologising,
thanking, saying goodbye, reacting, and light small talk).

This module is self-contained and uses only the standard library, so it is safe
to import in any runtime that already loads the other voice tools.

Example
-------
>>> casual_phrase("greeting")
{'intent': 'greeting', 'phrase': 'Oh hey!', 'alternatives': [...], 'fallback': False, 'requested_intent': 'greeting'}
>>> casual_phrase("hmm", seed="turn-12", count=2)
{'intent': 'thinking', 'phrase': 'Hmm, let me think...', ...}
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional

__all__ = ["casual_phrase", "available_intents"]

DEFAULT_INTENT = "acknowledge"
MAX_PHRASES = 5

# Canonical intent -> pool of interchangeable casual phrases.
PHRASES: Dict[str, List[str]] = {
    "greeting": [
        "Hey there!",
        "Oh hey!",
        "Hi! Good to hear from you.",
        "Hey, what's up?",
        "Hello! How's it going?",
        "Hiya!",
    ],
    "acknowledge": [
        "Got it.",
        "Okay, sure.",
        "Yep, gotcha.",
        "Right, right.",
        "Mm-hmm.",
        "Alright.",
        "Sure thing.",
    ],
    "thinking": [
        "Hmm, let me think...",
        "Good question...",
        "Hmm, one sec.",
        "Let me see...",
        "Hang on a moment...",
        "Hmm...",
    ],
    "agree": [
        "Yeah, totally.",
        "For sure.",
        "Absolutely.",
        "Yeah, I'm with you.",
        "Exactly, right?",
        "Yep, agreed.",
    ],
    "disagree": [
        "Eh, I'm not so sure.",
        "Hmm, I see it a bit differently.",
        "Yeah, but... maybe not.",
        "I don't know about that one.",
        "Fair, but I'd push back a little.",
    ],
    "apology": [
        "Oh, my bad.",
        "Sorry about that!",
        "Oops, sorry!",
        "Yeah, that one's on me.",
        "Sorry, I got that wrong.",
    ],
    "thanks": [
        "Thanks, I appreciate it!",
        "Oh, thank you!",
        "Thanks a bunch!",
        "Cheers, thanks!",
    ],
    "goodbye": [
        "Alright, catch you later!",
        "Talk soon!",
        "Take care!",
        "Bye for now!",
        "See ya!",
    ],
    "surprise": [
        "Wait, really?",
        "No way!",
        "Whoa, seriously?",
        "Oh wow!",
        "That's wild!",
    ],
    "sympathy": [
        "Aw, that sucks, I'm sorry.",
        "Oh no, that's rough.",
        "Ugh, I'm sorry to hear that.",
        "That's a bummer, hang in there.",
    ],
    "celebrate": [
        "Nice, congrats!",
        "Awesome, way to go!",
        "Yes! That's great news!",
        "Woohoo, nicely done!",
    ],
    "smalltalk": [
        "So, how's your day going?",
        "Anything fun going on today?",
        "How've you been?",
        "What's new with you?",
        "Busy day?",
    ],
}

# Everyday words a voice agent might pass in that map onto a canonical intent.
ALIASES: Dict[str, str] = {
    "greet": "greeting",
    "greetings": "greeting",
    "hello": "greeting",
    "hi": "greeting",
    "hey": "greeting",
    "welcome": "greeting",
    "ok": "acknowledge",
    "okay": "acknowledge",
    "got_it": "acknowledge",
    "understood": "acknowledge",
    "confirm": "acknowledge",
    "filler": "thinking",
    "stall": "thinking",
    "hesitate": "thinking",
    "hmm": "thinking",
    "pause": "thinking",
    "yes": "agree",
    "yep": "agree",
    "agreement": "agree",
    "no": "disagree",
    "nope": "disagree",
    "objection": "disagree",
    "sorry": "apology",
    "apologise": "apology",
    "apologize": "apology",
    "oops": "apology",
    "thank": "thanks",
    "thanks": "thanks",
    "thank_you": "thanks",
    "gratitude": "thanks",
    "bye": "goodbye",
    "farewell": "goodbye",
    "goodby": "goodbye",
    "see_you": "goodbye",
    "wow": "surprise",
    "shock": "surprise",
    "amazed": "surprise",
    "condolence": "sympathy",
    "comfort": "sympathy",
    "empathy": "sympathy",
    "congrats": "celebrate",
    "congratulations": "celebrate",
    "cheer": "celebrate",
    "chat": "smalltalk",
    "banter": "smalltalk",
    "chitchat": "smalltalk",
    "small_talk": "smalltalk",
    "weather_chat": "smalltalk",
}


def available_intents() -> List[str]:
    """Return the sorted list of canonical intents this tool can speak for."""
    return sorted(PHRASES)


def _normalize_intent(intent: Optional[str]) -> str:
    """Map a loose user-supplied intent name onto a canonical intent."""
    if not intent or not str(intent).strip():
        return DEFAULT_INTENT
    key = str(intent).strip().lower()
    for ch in ("-", " ", "/"):
        key = key.replace(ch, "_")
    while "__" in key:
        key = key.replace("__", "_")
    if key in PHRASES:
        return key
    if key in ALIASES:
        return ALIASES[key]
    stripped = key.rstrip("s")
    if stripped in PHRASES:
        return stripped
    if stripped in ALIASES:
        return ALIASES[stripped]
    return DEFAULT_INTENT


def _rng(seed: Optional[str], intent: str, count: int) -> random.Random:
    """Build a random source: deterministic when a seed is supplied."""
    if seed is None:
        return random.Random()
    material = "{}|{}|{}".format(seed, intent, count).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _clamp_count(count: int, pool_size: int) -> int:
    try:
        value = int(count)
    except (TypeError, ValueError):
        value = 1
    if value < 1:
        value = 1
    if value > MAX_PHRASES:
        value = MAX_PHRASES
    return min(value, pool_size)


def casual_phrase(
    intent: str = DEFAULT_INTENT,
    seed: Optional[str] = None,
    count: int = 1,
) -> Dict[str, object]:
    """Return a short casual phrase (plus alternatives) for a conversational intent.

    Args:
        intent: What the agent wants to say, e.g. ``"greeting"``, ``"thinking"``,
            ``"agree"``, ``"apology"``, ``"goodbye"``, ``"sympathy"``.
            Loose synonyms such as ``"hi"``, ``"hmm"``, ``"sorry"`` or ``"bye"``
            are accepted. Unknown values fall back to ``"acknowledge"``.
        seed: Optional string that makes the choice reproducible (e.g. a turn id).
            When omitted, a fresh random phrase is chosen each call.
        count: How many phrases to return, 1-5. The first is the suggested phrase;
            the rest are alternatives.

    Returns:
        A dict with keys ``intent`` (canonical intent used), ``phrase`` (the
        suggested spoken line), ``alternatives`` (list of other options),
        ``requested_intent`` (what was passed in) and ``fallback`` (True when the
        request could not be matched to a known intent).
    """
    requested = "" if intent is None else str(intent)
    canonical = _normalize_intent(intent)
    fallback = bool(requested.strip()) and requested.strip().lower().replace("-", "_").replace(" ", "_") != canonical

    pool = PHRASES.get(canonical) or PHRASES[DEFAULT_INTENT]
    wanted = _clamp_count(count, len(pool))
    rng = _rng(seed, canonical, wanted)

    picked = rng.sample(pool, wanted)
    return {
        "intent": canonical,
        "phrase": picked[0],
        "alternatives": picked[1:],
        "requested_intent": requested,
        "fallback": fallback,
    }
