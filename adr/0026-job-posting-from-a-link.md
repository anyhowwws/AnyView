# 0026 — A job posting can come from a link, fetched by the API

- **Status:** Accepted
- **Date:** 2026-10-14
- **Extends:** 0014 ("One target job, two ways in"), 0025 (saved jobs)

## Context

A target job came in two ways: upload the posting as a PDF or Word file, or
fill in the fields. Postings live on web pages, so in practice candidates were
turning the page into a PDF first, often by asking an AI to do it, just to
upload it here. That is a chore with no value, and a rewritten copy can drop or
change what the posting actually says.

Two ways to read a link were weighed:

1. **The API fetches the page** and turns the HTML into text itself.
2. **Gemini's URL-context tool**: hand the URL to the model and let Google's
   fetcher read it.

Option 2 has no server-side fetch, so there is nothing to protect against
request forgery. But the "posting text" that becomes `job_description` would be
the model's rewrite rather than the page. ADR 0025 matches saved jobs on that
exact text, so the same link could produce two saved jobs. It would also add a
tool-use path to `llm/adapter.py`, and some job sites block Google's fetcher.

## Decision

**The API fetches the page.** `POST /interview/job/parse-link {url}` fetches
it, turns it into text, and sends the text through the same function as an
uploaded posting (`_read_posting`): truncated to `MAX_JD_CHARS`, matched
against saved jobs, otherwise parsed into the setup form's fields. Everything
after the fetch is the upload path, unchanged. A link to a PDF is read by the
model, the same way an uploaded PDF is.

The setup form keeps its "Upload a posting" tab, with a link field under the
drop zone. The saved job's `source` stays `upload`: it is a posting whose text
the prompt carries, read-only. Where the text came from does not change how it
is edited.

### Fetching a URL a user typed

Server-side request forgery is the risk. On Cloud Run the prize is the metadata
server (`169.254.169.254`), which hands out the service account's token.
`uploads/link.py` checks every hop, redirects included:

- `http` or `https` only, on the default port, with no credentials in the URL.
- The hostname must resolve to public addresses only (`ipaddress.is_global`).
  If even one address is private, the link is refused.
- The request goes **to the address that was checked**. The `Host` header and
  the TLS name (`sni_hostname`) stay the real hostname, so certificates are
  still verified. Without this, a DNS answer that changes between the check and
  the fetch (DNS rebinding) could slip a private address past the check.
- Redirects are followed by hand, at most 5, and each one is checked again.
- 10 s timeout, 3 MB cap read as a stream, and only HTML, plain text or PDF
  is accepted.

The route sits behind the sign-in gate and the email allow-list (ADR 0009), so
only allow-listed users can make the API fetch anything.

### HTML to text, with the standard library

`html.parser` from the standard library, with no new parsing dependency.
`httpx` was already a test dependency and is now a runtime one, because it
supports `sni_hostname`, which the address pinning needs.

- A schema.org `JobPosting` in the page's JSON-LD is preferred when it has
  real content. Most applicant-tracking systems (Greenhouse, Lever, Workday)
  publish one, and it is often present even when the visible page is built by
  JavaScript.
- Otherwise the visible text, starting at the first `<h1>` (the job title on
  any job page), so the site's menus are not part of the posting. Scripts,
  styles, `nav`, `footer` and forms are dropped. List items keep their `- `.

## Consequences

- No new infrastructure. Cloud Run already has direct internet egress. There is
  no VPC connector, so no egress rule needed changing.
- Some links will not work: pages behind a login (LinkedIn), and pages built
  entirely by JavaScript that publish no JSON-LD. Both get a message telling
  the user to save the posting as a PDF and upload it. The API does not run a
  headless browser. That would be a large dependency and a much bigger attack
  surface.
- This is one fetch of one page, made because the user asked for it. It is not
  crawling and it is not the scraping the brief rules out (Glassdoor, Blind).
- Nothing about the URL is stored. The saved job holds the text, as before.
