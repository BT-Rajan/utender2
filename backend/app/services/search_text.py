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


# Common types of work, English and Arabic, as normalized stems: a search for
# one also finds the others ("electrical" finds "كهرباء", "AC" finds "تكييف").
SYNONYMS = [
    ["electric", "كهربا", "كهربايي"],
    ["plumb", "سباك", "صحي"],
    ["paint", "دهان", "صبغ"],
    ["ac", "a/c", "air condition", "hvac", "تكييف", "مكيف"],
    ["carpent", "joiner", "نجار"],
    ["tile", "tiling", "بلاط", "سيراميك"],
    ["roof", "سطح"],
    ["clean", "تنظيف"],
    ["landscap", "garden", "زراع", "حدايق", "حديقه"],
    ["weld", "steel work", "لحام", "حداد"],
    ["glass", "glaz", "زجاج"],
    ["insulat", "waterproof", "عزل"],
    ["demoli", "هدم"],
    ["concret", "خرسان"],
    ["gypsum", "plaster", "جبس"],
    ["light", "انار", "اضاء"],
    ["maint", "repair", "صيان", "تصليح"],
]


def _related(a: str, b: str) -> bool:
    return a == b or (len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)))


def _distance(a: str, b: str, cap: int) -> int:
    """Edit distance, giving up (returning cap + 1) once it exceeds cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > cap:
            return cap + 1
        previous = current
    return previous[-1]


def expand(word: str, vocabulary: set[str] = frozenset()) -> list[str]:
    """What a typed (normalized, stemmed) word may match: itself, its
    synonyms, and -- for typos -- words from `vocabulary` (what open
    opportunities actually say) within one edit (two for long words) of it,
    compared over the word's own length so a stem matches a longer word."""
    terms = {word}
    for group in SYNONYMS:
        if any(_related(word, member) for member in group):
            terms.update(group)
    if len(word) >= 5:
        cap = 2 if len(word) >= 8 else 1
        for candidate in vocabulary:
            if candidate in terms or len(candidate) < len(word) - cap:
                continue
            if _distance(word, candidate[: len(word)], cap) <= cap or _distance(word, candidate, cap) <= cap:
                terms.add(candidate[: len(word)] if len(candidate) > len(word) else candidate)
    return sorted(terms)


_AR = re.compile("^[؀-ۿ]+$")
_ROOT_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
_ROOT_SUFFIXES = ("ات", "ون", "ين", "ان", "ها", "هم", "يه", "ه", "ي")
_DERIVATION = ("م", "ت", "ا", "ي", "ن")
_LONG_VOWELS = ("ا", "و", "ي")


def arabic_root(word: str) -> str | None:
    """A light root for one normalized Arabic word -- strip the article,
    common endings, one derivational prefix and long-vowel infixes -- so
    words built on the same root meet ("تكييف", "مكيفات", "مكيف" -> "كيف";
    "دهان", "دهانات" -> "دهن"). Three or four letters, or None when the word
    doesn't reduce to one. Deliberately approximate: used only as a further
    way for a search to match, never to exclude."""
    if not _AR.match(word or "") or len(word) < 3:
        return None
    for p in _ROOT_PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 3:
            word = word[len(p):]
            break
    for s in _ROOT_SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= 3:
            word = word[: -len(s)]
            break
    # م/ت (place, verbal noun) on four letters or more; ا/ي/ن only on longer
    # words, where they are much more likely a prefix than part of the root.
    if (len(word) >= 4 and word[0] in "مت") or (len(word) >= 5 and word[0] in _DERIVATION):
        word = word[1:]
    while len(word) > 3:
        inner = next((i for i in range(1, len(word) - 1) if word[i] in _LONG_VOWELS), None)
        if inner is None:
            break
        word = word[:inner] + word[inner + 1:]
    return word if 3 <= len(word) <= 4 else None


def roots_of(text: str | None) -> str | None:
    """The distinct Arabic roots in a (normalized) text, space-delimited with
    a space at each end so a root can be matched as a whole token."""
    roots = sorted({r for w in normalize(text).split() if (r := arabic_root(w))})
    return (" " + " ".join(roots) + " ") if roots else None
