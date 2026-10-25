"""Deterministic allergen check on top of the prompt.

The prompt is the primary guard; this is a safety net that does not trust the model. Matching is
deliberately crude and errs on the side of false positives: a false alarm costs one regeneration,
a miss can cost an allergic reaction.
"""

import re
from collections.abc import Iterable

from app.schemas.recipes import RecipeContent

_WORD_RE = re.compile(r"[\w'’]+")


def _stem(word: str) -> str:
    """Drop the Ukrainian inflection, so 'яйця' matches 'яйце', 'арахіс' matches 'арахісова'."""
    if len(word) <= 3:
        return word
    return word[:-1] if len(word) <= 5 else word[:-2]


def find_allergens(allergies: Iterable[str], texts: Iterable[str]) -> list[str]:
    """Allergies found in any of the texts: every word of the allergy starts a word of the text."""
    text_words = [_WORD_RE.findall(t.casefold()) for t in texts]
    found: list[str] = []
    for allergy in allergies:
        stems = [_stem(w) for w in _WORD_RE.findall(allergy.casefold())]
        if stems and any(
            all(any(w.startswith(s) for w in words) for s in stems) for words in text_words
        ):
            found.append(allergy)
    return found


def recipe_texts(content: RecipeContent) -> list[str]:
    """Where an allergen can hide: ingredient names, and steps (garnishes are often only there)."""
    return [i.name for i in content.ingredients] + content.steps
