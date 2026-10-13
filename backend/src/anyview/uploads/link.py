"""A job posting fetched from a link the user pasted (ADR 0026).

The API fetches one page, on request, for a signed-in user, and turns it into
the same plain text an uploaded posting becomes. From there it goes down the
same path: saved-job match, then the parse call.

Fetching a URL someone else typed is how a server gets tricked into reading
its own internals (server-side request forgery). On Cloud Run the prize is the
metadata server at 169.254.169.254, which hands out the service account's
access token. So every hop, redirects included:

  - is http or https on the default port,
  - resolves to public addresses only (`ipaddress.is_global`),
  - is then fetched *from the address we checked*, not by resolving the name a
    second time, so a DNS answer that changes between check and fetch (DNS
    rebinding) cannot slip a private address in. TLS still verifies the
    certificate against the real hostname (`sni_hostname`).

The body is capped, the whole fetch has a timeout, and only HTML, plain text
and PDF are accepted.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from anyview.uploads.extract import ExtractionError

MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 10.0
DEFAULT_PORTS = {"http": 80, "https": 443}

HTML_TYPES = {"text/html", "application/xhtml+xml"}
TEXT = "text/plain"
PDF = "application/pdf"

# Some job sites answer a bare client with a 403; a browser-like identity with
# our name in it is honest and gets the page.
USER_AGENT = "Mozilla/5.0 (compatible; AnyView/1.0; job posting reader)"

# `resolve(host)` returns the host's addresses. Swappable so tests never touch DNS.
Resolver = Callable[[str], list[str]]


@dataclass
class Page:
    url: str  # where we ended up, after redirects
    content_type: str  # media type only, no parameters
    body: bytes
    charset: str | None


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ExtractionError("That address doesn't exist. Check the link.") from exc
    # Each info is (family, type, proto, canonname, sockaddr); sockaddr[0] is the IP.
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def _public_address(host: str, resolve: Resolver) -> str:
    """The first address of `host`, refusing the lot if any of them is not
    public. A name that resolves to one public and one private address is
    treated as private: we don't get to pick which one a retry would use."""
    addresses = resolve(host)
    if not addresses:
        raise ExtractionError("That address doesn't exist. Check the link.")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise ExtractionError("That link points somewhere private. Paste a public job page.")
    return addresses[0]


def _checked(url: str) -> tuple[httpx.URL, str]:
    """`url` parsed, scheme/port/host checked. Returns the URL and its host."""
    parts = urlsplit(url.strip())
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
        raise ExtractionError("Paste the full link, starting with https://.")
    if parts.username or parts.password:
        raise ExtractionError("Paste the link without a username or password in it.")
    try:
        port = parts.port
    except ValueError as exc:  # a port like ":99999" or ":abc"
        raise ExtractionError("That link isn't valid. Check it and try again.") from exc
    if port not in (None, DEFAULT_PORTS[parts.scheme]):
        raise ExtractionError("Job pages live on the normal web ports. Check the link.")
    return httpx.URL(url.strip()), parts.hostname


def fetch(url: str, *, resolve: Resolver = _resolve, transport=None) -> Page:
    """Fetch one page, following up to MAX_REDIRECTS redirects, checking every hop."""
    with httpx.Client(
        transport=transport,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,  # we follow them ourselves, so each hop is checked
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/pdf"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            target, host = _checked(url)
            address = _public_address(host, resolve)
            # Connect to the checked address; the Host header and TLS name stay
            # the real hostname so virtual hosting and certificates still work.
            pinned = target.copy_with(host=address)
            request = client.build_request(
                "GET",
                pinned,
                headers={"Host": target.netloc.decode("ascii")},
                extensions={"sni_hostname": host},
            )
            try:
                response = client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise ExtractionError("That page took too long to answer. Try again.") from exc
            except httpx.HTTPError as exc:
                raise ExtractionError("Couldn't reach that page. Check the link.") from exc
            try:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    url = urljoin(str(target), location)
                    continue
                if response.status_code in (401, 403):
                    raise ExtractionError(
                        "That site won't show the posting without signing in. "
                        "Save it as a PDF and upload that instead."
                    )
                if response.status_code == 404:
                    raise ExtractionError("That posting isn't there any more. Check the link.")
                if response.status_code >= 400:
                    raise ExtractionError(
                        f"That site answered with an error ({response.status_code}). Try again."
                    )
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type not in HTML_TYPES | {TEXT, PDF}:
                    raise ExtractionError("That link isn't a web page or a PDF.")
                body = _read_capped(response)
                return Page(str(target), content_type.lower(), body, response.charset_encoding)
            finally:
                response.close()
    raise ExtractionError("That link redirects too many times.")


def _read_capped(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_PAGE_BYTES:
                raise ExtractionError("That page is too large to be a job posting.")
            chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ExtractionError("The page stopped loading part-way. Try again.") from exc
    return b"".join(chunks)


# --- HTML to text ------------------------------------------------------------

# Never text a reader would call the posting. Not `head`: `</head>` may be left
# out of valid HTML, and skipping to a close tag that never comes loses the page.
SKIP = {"script", "style", "noscript", "template", "svg", "title", "nav", "footer", "form",
        "button", "select", "iframe", "dialog"}  # fmt: skip
# Tags that start a new line, so paragraphs and list items stay apart.
BLOCK = {"p", "div", "section", "article", "main", "header", "aside", "ul", "ol", "li", "dl",
         "dt", "dd", "table", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
         "br", "hr"}  # fmt: skip
# Tags with no closing tag; they must not open a skip region.
VOID = {"br", "hr", "img", "meta", "link", "input", "source", "wbr", "area", "col", "embed"}


class _TextParser(HTMLParser):
    """Walks the HTML once. Collects the readable text, and on the side any
    JSON-LD blocks, which is where most applicant-tracking systems put a
    clean copy of the posting (schema.org `JobPosting`)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # turns &amp; etc. into characters
        self.parts: list[str] = []
        self.json_ld: list[str] = []
        self._skipping: list[str] = []  # stack of open tags we are inside and ignoring
        self._in_json_ld = False
        # Where the first <h1> starts in `parts`: on a job page, the job title.
        # Menus above it are not the posting.
        self.h1_at: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and ("type", "application/ld+json") in attrs:
            self._in_json_ld = True
            self.json_ld.append("")  # one entry per block; handle_data may arrive in pieces
        if self._skipping or tag in SKIP:
            if tag not in VOID:
                self._skipping.append(tag)
            return
        if tag == "h1" and self.h1_at is None:
            self.h1_at = len(self.parts)
        if tag in BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if self._skipping:
            # Close the innermost matching tag; a stray end tag is ignored.
            if tag in self._skipping:
                while self._skipping.pop() != tag:
                    pass
            if tag == "script":
                self._in_json_ld = False
            return
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self.json_ld[-1] += data
        elif not self._skipping:
            self.parts.append(data)


def _tidy(text: str) -> str:
    """Collapse runs of spaces, drop blank lines and lines repeated back to back."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line and line != "-" and (not lines or lines[-1] != line):
            lines.append(line)
    return "\n".join(lines)


def html_to_text(html: str) -> str:
    """The readable text of an HTML page or fragment."""
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    return _tidy("".join(parser.parts))


def _job_postings(blocks: list[str]) -> list[dict]:
    """Every schema.org JobPosting in the page's JSON-LD, wherever it is nested."""
    found: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = node.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                found.append(node)
            walk(node.get("@graph", []))

    for block in blocks:
        try:
            walk(json.loads(block))
        except ValueError:  # malformed JSON-LD is common; ignore it
            continue
    return found


def _name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _from_job_posting(posting: dict) -> str:
    """A JobPosting's fields as plain text, title first."""
    lines = [_name(posting.get("title"))]
    if company := _name(posting.get("hiringOrganization")):
        lines.append(f"Company: {company}")
    locations = posting.get("jobLocation")
    for place in locations if isinstance(locations, list) else [locations]:
        address = place.get("address") if isinstance(place, dict) else None
        if isinstance(address, dict):
            bits = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            where = ", ".join(_name(b) for b in bits if b)
            if where:
                lines.append(f"Location: {where}")
    if kind := posting.get("employmentType"):
        lines.append(f"Employment type: {kind if isinstance(kind, str) else ', '.join(kind)}")
    lines.append(html_to_text(str(posting.get("description") or "")))
    for key, label in (
        ("qualifications", "Qualifications"),
        ("responsibilities", "Responsibilities"),
    ):
        if value := posting.get(key):
            lines.append(f"{label}:\n{html_to_text(str(value))}")
    return _tidy("\n".join(lines))


def page_to_text(html: str) -> str:
    """A job page as text. A JobPosting in the page's JSON-LD is preferred:
    it is the posting alone, without menus and footers, and it is often there
    even when the visible page is built by JavaScript the API never runs.
    Otherwise the visible text, from the first <h1> (the job title) onwards."""
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    postings = _job_postings(parser.json_ld)
    if postings:
        text = _from_job_posting(postings[0])
        if len(text) >= 200:  # a stub with just a title is worse than the page
            return text
    if parser.h1_at is not None:
        from_title = _tidy("".join(parser.parts[parser.h1_at :]))
        if len(from_title) >= 200:
            return from_title
    return _tidy("".join(parser.parts))
