"""Finding a quote in a dump, and finding which part of a dump belongs to whom.

Every draft and every skill link carries a verbatim quote (ADR 0002, 0019).
"Verbatim" has to survive what happens between a PDF and a model: a resume
says "Apr 2026 – Present" with an en dash, the model quotes it with a hyphen;
a bullet is "•" in one place and "·" in another. `fold()` makes those the
same before any comparison, and nothing else: words, numbers and their order
still have to match.

`spans()` answers the linking pass's question (ADR 0019): which stretch of the
dump is this role's or this project's own text? A quote justifies a link only
if it sits inside the target's stretch.
"""

from __future__ import annotations

import bisect
import re
import unicodedata

from anyview.brain.models import Patch

# Characters that differ between a document and a model's copy of it without
# changing what the text says. Dashes become "-", list markers become spaces,
# curly quotes become straight ones.
_FOLD = str.maketrans(
    {
        "–": "-", "—": "-", "‐": "-", "‑": "-", "‒": "-", "−": "-",
        "•": " ", "·": " ", "▪": " ", "●": " ", "◦": " ",
        "‘": "'", "’": "'", "“": '"', "”": '"',
    }
)  # fmt: skip


# A line break followed by a list marker or a blank line: where a bullet ends.
_NEXT_BULLET = re.compile(r"\n[ \t]*(?:[-•·▪●◦*]\s|\n)")


def fold(text: str) -> tuple[str, list[int]]:
    """The comparable form of `text`, plus where each of its characters came
    from in the original.

    Comparable means: Unicode-normalised (NFKC turns ligatures like "ﬁ" into
    "fi"), punctuation folded as above, case-folded, and every run of
    whitespace collapsed to one space. The position list lets a match found
    in the folded text be cut back out of the original, so a prompt can show
    the user's own wording rather than a lower-cased copy.
    """
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch).translate(_FOLD).casefold():
            if c.isspace():
                if not out or out[-1] == " ":
                    continue
                c = " "
            out.append(c)
            where.append(i)
    if out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), where


def normalise(text: str) -> str:
    return fold(text)[0]


# Where a model joins two lines of a document into one quote, it puts its own
# separator in the seam: "Architect | Lenovo PCCW" for a title on one line and
# the employer on the next.
_SEAM = re.compile(r"\s*(?:\||·|•|\n|\s[-–—]\s)\s*")
# What may sit between two pieces in the document: separators and spaces only,
# a few characters at most. Words in between mean the pieces are not adjacent.
_GAP = re.compile(r"[\s|·•/,;:\-]{0,5}")


def locate(folded: str, quote: str, lo: int = 0) -> tuple[int, int] | None:
    """Where the quote sits in the folded text, from `lo` on, as (start, end).

    First as written. Failing that, as verbatim pieces split at the seams a
    model adds when it joins adjacent lines, each piece found right after the
    one before with only separators between. Every word is still the
    document's own, in the document's order.
    """
    needle = normalise(quote)
    if not needle:
        return None
    at = folded.find(needle, lo)
    if at != -1:
        return at, at + len(needle)
    pieces = [normalise(p) for p in _SEAM.split(quote)]
    pieces = [p for p in pieces if p]
    if len(pieces) < 2:
        return None
    start = folded.find(pieces[0], lo)
    while start != -1:
        end = start + len(pieces[0])
        for piece in pieces[1:]:
            gap = _GAP.match(folded, end)
            nxt = gap.end() if gap else end
            # the gap match is greedy; the piece may begin with a separator
            candidates = [i for i in range(end, nxt + 1) if folded.startswith(piece, i)]
            if not candidates:
                break
            end = candidates[0] + len(piece)
        else:
            return start, end
        start = folded.find(pieces[0], start + 1)
    return None


def contains(haystack: str, quote: str) -> bool:
    """Is `quote` in `haystack`, once both are folded? An empty quote is not."""
    return locate(normalise(haystack), quote) is not None


def within(folded: str, quote: str, lo: int, hi: int) -> bool:
    """Does the folded `quote` occur entirely inside folded[lo:hi]?"""
    found = locate(folded, quote, lo)
    return found is not None and found[1] <= hi


def spans(patch: Patch, text: str) -> dict[str, tuple[int, int]]:
    """Each verified role's and project's own stretch of the *folded* dump, by key.

    A draft's stretch starts where its evidence quote does. A project's ends
    at the end of its bullet (the next line that starts a new bullet, or a
    blank line) or where the next role or project starts, whichever is first:
    the bullet after it may be a responsibility, not part of the project. A
    role's ends where the next role starts, so it covers its projects and its
    ongoing work alike. A credential's stretch is its own evidence quote and
    nothing more (ADR 0020): certifications sit in lists, where the next
    words belong to the next credential. A draft whose quote cannot be found
    has no stretch, and nothing links to it.
    """
    folded, where = fold(text)
    starts: list[tuple[int, str, str]] = []  # (position, kind, key)
    for kind, drafts in (("role", patch.roles), ("project", patch.projects)):
        for d in drafts:
            if d.unverified:
                continue
            found = locate(folded, d.evidence)
            if found:
                starts.append((found[0], kind, d.key))
    starts.sort()
    out: dict[str, tuple[int, int]] = {}
    for i, (at, kind, key) in enumerate(starts):
        later = [s for s in starts[i + 1 :] if s[0] > at and (kind == "project" or s[1] == "role")]
        end = later[0][0] if later else len(folded)
        if kind == "project":
            bullet_end = _NEXT_BULLET.search(text, where[at])
            if bullet_end:
                # Back from the original's coordinates to the folded text's.
                end = min(end, bisect.bisect_left(where, bullet_end.start()))
        out[key] = (at, end)
    for d in patch.achievements:
        found = locate(folded, d.evidence) if d.kind == "credential" and not d.unverified else None
        if found:
            out[d.key] = found
    return out
