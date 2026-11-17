"""Arabic/English normalization for search (ADR-06), language detection, identifier extraction."""
import re

_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL = "\u0640"
_ALEF = re.compile(r"[\u0622\u0623\u0625\u0671]")  # آ أ إ ٱ -> ا
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_WS = re.compile(r"\s+")
_ARABIC_LETTER = re.compile(r"[\u0621-\u064A]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[\w]+", re.UNICODE)

IDENTIFIER = re.compile(
    r"(?<![\w])(?:"
    r"[A-Za-z][A-Za-z0-9]*(?:[_\-.][A-Za-z0-9]+)+"      # snake_case, kebab-case, dotted.names, ERR_4012
    r"|[a-z]+[A-Z][A-Za-z0-9]*"                          # camelCase: getSubscriberProfile
    r"|[A-Z]{2,}[0-9]+[A-Z0-9]*"                         # codes: E1001, HTTP503
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"  # UUIDs
    r"|[A-Za-z]*[0-9]{3,}[A-Za-z0-9]*"                   # transaction ids, numbers in codes
    r")(?![\w])")

STOPWORDS = set("""a an the is are was were be been of to in on for and or but with what which who how why when where
do does did can could should would will this that these those it its as at by from about into than then there here
please explain tell me show give list i we you my our your
ما ماذا من في على عن إلى الى هل كيف لماذا متى أين اين هذا هذه ذلك التي الذي هو هي و أو او ثم مع""".split())


def normalize(text: str) -> str:
    """Search form of a text: original casing and content otherwise preserved for identifiers."""
    text = _TASHKEEL.sub("", text).replace(_TATWEEL, "")
    text = _ALEF.sub("ا", text).replace("ة", "ه").replace("ى", "ي")
    text = text.translate(_DIGITS)
    return _WS.sub(" ", text).strip()


def detect_language(text: str) -> str:
    ar = len(_ARABIC_LETTER.findall(text))
    en = len(_LATIN_LETTER.findall(text))
    if ar + en == 0:
        return "en"
    share = ar / (ar + en)
    return "ar" if share > 0.6 else "en" if share < 0.2 else "mixed"


def identifiers(text: str) -> list[str]:
    seen, out = set(), []
    for match in IDENTIFIER.findall(text):
        if len(match) >= 4 and match.lower() not in seen:
            seen.add(match.lower())
            out.append(match)
    return out


def query_terms(text: str) -> list[str]:
    terms = []
    for word in _WORD.findall(normalize(text).lower()):
        if word not in STOPWORDS and len(word) > 1 and word not in terms:
            terms.append(word)
    return terms[:24]
