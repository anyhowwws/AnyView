"""A job posting from a pasted link (ADR 0026). No network: DNS is a dict and
HTTP is an `httpx.MockTransport`, a fake server that answers in-process."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from anyview.api import interview
from anyview.llm.fake import FakeModel
from anyview.main import app
from anyview.uploads import link
from anyview.uploads.extract import ExtractionError
from anyview.uploads.link import Page, fetch, page_to_text

POSTING = """
<html><head><title>Cloud Architect</title><script>var tracking = 1;</script></head>
<body>
  <div class="menu"><a>Home</a><a>Teams</a><ul><li>My applications</li></ul></div>
  <h1>Cloud Architect, Managed Services</h1>
  <div>Job ID: 10457888 | Initech Singapore</div>
  <h2>Description</h2>
  <p>You will help our largest customers navigate the operational challenges of cloud
  computing &amp; advise on their architecture.</p>
  <h2>Basic Qualifications</h2>
  <ul><li>5+ years of design and architecture experience</li>
      <li>5+ years of cloud based solution experience</li></ul>
  <nav>Careers Teams Locations</nav>
  <footer>&copy; Initech</footer>
</body></html>
"""


# --- HTML to text ------------------------------------------------------------


def test_page_text_starts_at_the_title_and_keeps_lists():
    text = page_to_text(POSTING)
    assert text.startswith("Cloud Architect, Managed Services")
    assert "- 5+ years of design and architecture experience" in text
    assert "computing & advise" in text  # entities decoded, lines joined
    for noise in ("Home", "My applications", "tracking", "Careers", "Initech\n"):
        assert noise not in text


def test_a_json_ld_job_posting_is_preferred_to_the_page():
    posting = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Initech"},
            {
                "@type": "JobPosting",
                "title": "Platform Engineer",
                "hiringOrganization": {"@type": "Organization", "name": "Initech"},
                "jobLocation": {"address": {"addressLocality": "Singapore"}},
                "employmentType": ["FULL_TIME"],
                "description": "<p>Own the platform roadmap.</p><ul><li>Terraform</li></ul>"
                + "<p>"
                + "Guardrails other teams build on. " * 8
                + "</p>",
            },
        ],
    }
    html = (
        "<html><body><div id=app></div>"
        f'<script type="application/ld+json">{json.dumps(posting)}</script></body></html>'
    )
    text = page_to_text(html)
    assert text.splitlines()[:4] == [
        "Platform Engineer",
        "Company: Initech",
        "Location: Singapore",
        "Employment type: FULL_TIME",
    ]
    assert "- Terraform" in text


def test_a_missing_head_close_tag_does_not_lose_the_page():
    html = POSTING.replace("</head>", "")
    assert page_to_text(html) == page_to_text(POSTING)


def test_a_page_built_by_javascript_has_almost_no_text():
    assert (
        page_to_text("<html><body><div id=root></div><script>render()</script></body></html>") == ""
    )


# --- Fetching, and what it refuses -------------------------------------------

PUBLIC = {"jobs.example.com": ["93.184.215.14"], "careers.example.com": ["93.184.215.15"]}


def _resolver(table):
    def resolve(host):
        if host not in table:
            raise ExtractionError("That address doesn't exist. Check the link.")
        return table[host]

    return resolve


def _fetch(url, handler, table=PUBLIC):
    return fetch(url, resolve=_resolver(table), transport=httpx.MockTransport(handler))


def test_fetch_connects_to_the_checked_address_under_the_real_name():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="ok")

    page = _fetch("https://jobs.example.com/en/jobs/1", handler)
    assert page.content_type == "text/html" and page.body == b"ok" and page.charset == "utf-8"
    (request,) = seen
    assert request.url.host == "93.184.215.14"  # pinned: no second DNS lookup
    assert request.headers["host"] == "jobs.example.com"
    assert request.extensions["sni_hostname"] == "jobs.example.com"  # TLS checks the real name


@pytest.mark.parametrize(
    "url",
    [
        "ftp://jobs.example.com/x",
        "file:///etc/passwd",
        "jobs.example.com/no-scheme",
        "https://jobs.example.com:8443/x",
        "https://user:pw@jobs.example.com/x",
    ],
)
def test_odd_links_are_refused_before_any_request(url):
    with pytest.raises(ExtractionError):
        _fetch(url, lambda r: pytest.fail("no request should be sent"))


@pytest.mark.parametrize(
    "address",
    ["169.254.169.254", "10.0.0.5", "127.0.0.1", "192.168.1.1", "::1", "fd00::1", "100.64.0.1"],
)
def test_private_addresses_are_refused(address):
    table = {"metadata.example.com": ["93.184.215.14", address]}  # one bad address is enough
    with pytest.raises(ExtractionError, match="private"):
        _fetch("http://metadata.example.com/", lambda r: pytest.fail("no request"), table)


def test_a_redirect_to_a_private_address_is_refused():
    table = {**PUBLIC, "internal.example.com": ["10.1.2.3"]}

    def handler(request):
        return httpx.Response(302, headers={"location": "http://internal.example.com/secrets"})

    with pytest.raises(ExtractionError, match="private"):
        _fetch("https://jobs.example.com/", handler, table)


def test_redirects_are_followed_to_a_public_page():
    def handler(request):
        if request.headers["host"] == "jobs.example.com":
            return httpx.Response(301, headers={"location": "https://careers.example.com/1"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="posting")

    page = _fetch("https://jobs.example.com/old", handler)
    assert page.url == "https://careers.example.com/1" and page.body == b"posting"


def test_endless_redirects_stop():
    def handler(request):
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(ExtractionError, match="too many"):
        _fetch("https://jobs.example.com/", handler)


def test_a_huge_page_is_refused(monkeypatch):
    monkeypatch.setattr(link, "MAX_PAGE_BYTES", 1000)

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 5000)

    with pytest.raises(ExtractionError, match="too large"):
        _fetch("https://jobs.example.com/", handler)


@pytest.mark.parametrize(
    ("status", "content_type", "message"),
    [
        (403, "text/html", "signing in"),
        (404, "text/html", "isn't there"),
        (500, "text/html", "error"),
        (200, "image/png", "isn't a web page"),
    ],
)
def test_unhelpful_answers_become_readable_messages(status, content_type, message):
    def handler(request):
        return httpx.Response(status, headers={"content-type": content_type}, content=b"")

    with pytest.raises(ExtractionError, match=message):
        _fetch("https://jobs.example.com/", handler)


# --- The route ----------------------------------------------------------------


@pytest.fixture
def client(signed_in):
    fake = FakeModel()
    pages: dict[str, Page] = {}

    def fetcher(url):
        if url not in pages:
            raise ExtractionError("Couldn't reach that page. Check the link.")
        return pages[url]

    app.dependency_overrides[interview.get_model] = lambda: fake
    app.dependency_overrides[interview.get_repository_optional] = lambda: None
    app.dependency_overrides[interview.get_page_fetcher] = lambda: fetcher
    c = TestClient(app, headers={"Authorization": "Bearer good"})
    c.fake, c.pages = fake, pages
    yield c
    for dep in (interview.get_model, interview.get_repository_optional, interview.get_page_fetcher):
        app.dependency_overrides.pop(dep, None)


def test_a_link_comes_back_as_text_and_prefilled_fields(client):
    url = "https://jobs.example.com/en/jobs/1"
    client.pages[url] = Page(url, "text/html", POSTING.encode(), "utf-8")
    r = client.post("/interview/job/parse-link", json={"url": url})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"].startswith("Cloud Architect, Managed Services")
    assert body["parsed"]["company"] == "Initech"  # the fake model's scripted parse
    (call,) = [c for c in client.fake.calls if c["call"] == "parse_job"]
    assert "Basic Qualifications" in call["user"]


def test_a_pdf_link_is_read_like_an_uploaded_pdf(client):
    url = "https://jobs.example.com/posting.pdf"
    client.pages[url] = Page(url, "application/pdf", b"%PDF-1.7 fake", None)
    r = client.post("/interview/job/parse-link", json={"url": url})
    assert r.status_code == 200, r.text
    assert [c["call"] for c in client.fake.calls] == ["extract", "parse_job"]


def test_a_link_that_cannot_be_read_is_a_readable_422(client):
    r = client.post("/interview/job/parse-link", json={"url": "https://nowhere.example.com/"})
    assert r.status_code == 422 and "Couldn't reach" in r.json()["detail"]

    url = "https://spa.example.com/job/1"
    client.pages[url] = Page(url, "text/html", b"<div id=root></div>", "utf-8")
    r = client.post("/interview/job/parse-link", json={"url": url})
    assert r.status_code == 422 and "upload" in r.json()["detail"]
