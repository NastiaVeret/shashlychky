"""Deterministic allergen check on top of the prompt.

The prompt is the primary guard; this is a safety net that does not trust the model. It has no
dictionary, so it works on stems: a text word matches an allergy word when it is the same stem
followed by a known Ukrainian noun or adjective ending. That keeps "молочний"/"яєчний"/"арахісова"
and rejects "молотий", "медальйони", "макарони", "маслини", "горілка", "сирий".
"""

import re
from collections.abc import Iterable

from app.schemas.recipes import RecipeContent

_WORD_RE = re.compile(r"[\w'’]+")

# Case/number endings of nouns, longest first so the longest suffix is stripped.
_NOUN_ENDINGS = (
    "ами", "ями", "ові", "еві", "єві", "ого", "ях", "ах", "ам", "ям", "ом", "ем", "єм",
    "ою", "ею", "єю", "ів", "їв", "ей", "ої", "ій",
    "а", "я", "у", "ю", "и", "і", "е", "о", "ь",
)  # fmt: skip
# Adjective endings that turn a food noun into "made of / containing it".
_ADJ_ENDINGS = (
    "ний", "на", "не", "ні", "ного", "ної", "ному", "ній", "ним", "ною", "них", "ними",
    "овий", "ова", "ове", "ові", "ового", "ової", "овому", "овим", "овою", "ових",
    "евий", "євий", "ева", "єва", "еве", "єве", "еві", "євого", "євої", "євим", "євих",
    "яний", "яна", "яне", "яні", "яного", "яної", "яним", "яних",
    "ячий", "яча", "яче", "ячі", "ячого", "ячої", "ячим", "ячих",
    "ковий", "кова", "кове", "кові",
)  # fmt: skip
_ALLOWED_ENDINGS = frozenset(_NOUN_ENDINGS) | frozenset(_ADJ_ENDINGS)
_MIN_STEM = 3
# Consonant alternation at the end of a stem: молок- → молоч-, горіх- → горіш-.
_ALTERNATIONS = {"к": "ч", "г": "ж", "х": "ш", "ц": "ч"}
# Irregular forms the ending rules cannot derive. Values are prefixes matched with any short tail.
_SYNONYM_STEMS: dict[str, tuple[str, ...]] = {
    "яйц": ("яєч", "яєць", "яєчн"),
    "яйце": ("яєч", "яєць"),
    "соя": ("соєв", "соєви"),
    "курк": ("куряч", "курят", "куриц"),
    "курят": ("куряч", "курк"),
    "горіх": ("горішк",),
    "молок": ("молочк",),
    "риб": ("рибн", "рибк"),
    "пшениц": ("пшеничн",),
    "глютен": ("глютенов", "клейковин"),
}
_SYNONYM_TAIL = 4


def _stem(word: str) -> str:
    for ending in _NOUN_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= _MIN_STEM:
            return word[: -len(ending)]
    return word


def _variants(stem: str) -> set[str]:
    variants = {stem}
    if stem and stem[-1] in _ALTERNATIONS:
        variants.add(stem[:-1] + _ALTERNATIONS[stem[-1]])
    return variants


def _word_matches(word: str, stem: str) -> bool:
    for variant in _variants(stem):
        if word == variant:
            return True
        if word.startswith(variant) and word[len(variant) :] in _ALLOWED_ENDINGS:
            return True
    for prefix in _SYNONYM_STEMS.get(stem, ()):
        if word.startswith(prefix) and len(word) - len(prefix) <= _SYNONYM_TAIL:
            return True
    return False


def find_allergens(allergies: Iterable[str], texts: Iterable[str]) -> list[str]:
    """Allergies found in any of the texts: every word of the allergy matches a word of the text."""
    text_words = [_WORD_RE.findall(t.casefold()) for t in texts]
    found: list[str] = []
    for allergy in allergies:
        stems = [_stem(w) for w in _WORD_RE.findall(allergy.casefold())]
        if stems and any(
            all(any(_word_matches(w, s) for w in words) for s in stems) for words in text_words
        ):
            found.append(allergy)
    return found


def recipe_texts(content: RecipeContent) -> list[str]:
    """Everywhere an allergen can hide: title, description, ingredient names, steps and tips."""
    texts = [content.title, content.description, *(i.name for i in content.ingredients)]
    texts.extend(content.steps)
    if content.tips:
        texts.append(content.tips)
    return texts
