"""Stage 4.2 follow-up: text normalisation for the provider feed's search.

Stored text (Project.search_* columns) and typed words go through the same
normalize(), so a search matches regardless of Arabic letter variants,
diacritics, Arabic-Indic digits or case. Typed words are also lightly
stemmed (stem_word), so "paints" finds "painting" and "الكهرباء" finds
"كهربائية" -- a plain substring match on the stem, in the database.
Deliberately small: no dictionary, no external search engine."""
import re

_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # tashkeel, Quranic marks, tatweel
_LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه", "ء": "",
    **{chr(0x0660 + d): str(d) for d in range(10)},  # Arabic-Indic digits
    **{chr(0x06F0 + d): str(d) for d in range(10)},  # Eastern Arabic-Indic digits
})
_SPACES = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    text = _DIACRITICS.sub("", text).translate(_LETTERS).casefold()
    return _SPACES.sub(" ", text).strip()


_AR_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال")
_AR_SUFFIXES = ("ات", "ون", "ين", "يه", "ه", "ي")
_EN_SUFFIXES = ("ings", "ing", "ers", "er", "ies", "es", "ed", "s")


def stem_word(word: str) -> str:
    """A light stem of one normalized word: common Arabic prefixes/suffixes
    and English endings, never leaving fewer than three letters."""
    if re.search("[؀-ۿ]", word):
        for p in _AR_PREFIXES:
            if word.startswith(p) and len(word) - len(p) >= 3:
                word = word[len(p):]
                break
        for s in _AR_SUFFIXES:
            if word.endswith(s) and len(word) - len(s) >= 3:
                return word[: -len(s)]
        return word
    for s in _EN_SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= 3:
            return word[: -len(s)]
    return word


def search_words(text: str, limit: int = 8) -> list[str]:
    """The typed search as normalized, stemmed words (at most `limit`)."""
    return [stem_word(w) for w in normalize(text).split()[:limit]]


# Governorates are stored as keys; searched by their English and Arabic names.
GOVERNORATE_NAMES = {
    "capital": "Capital Kuwait City العاصمة مدينة الكويت",
    "hawalli": "Hawalli حولي",
    "farwaniya": "Farwaniya الفروانية",
    "mubarak_al_kabeer": "Mubarak Al-Kabeer مبارك الكبير",
    "ahmadi": "Ahmadi الأحمدي",
    "jahra": "Jahra الجهراء",
}
