"""Fetch with a paid fallback. Direct fetch first (free, polite, robots.txt honoured); a scraping API only when the origin refuses.

The key is read from the environment variable ALTERLAB_API_KEY and from nowhere else. It is sent in one request header and is never
printed, logged or written. Without the key the pipeline behaves exactly as a direct-only run, and says so once.

Order: robots.txt (always, and it wins) -> direct GET -> only if the direct answer was 403, 429, 5xx or a page that needs JavaScript
-> POST /api/v1/scrape. A fallback is skipped for the rest of the run once ALTERLAB_MAX_USD (default 0.25) has been spent.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

from pipeline import adapters as A

Failure = A.Failure
from pipeline.adapters import USER_AGENT  # the same agent string the direct fetches send

ENDPOINT = 'https://alterlab.io/api/v1/scrape'
KEY_ENV, MAX_ENV, DEFAULT_MAX_USD = 'ALTERLAB_API_KEY', 'ALTERLAB_MAX_USD', 0.25
NOT_CONFIGURED = 'fallback fetcher: not configured'


class FetchError(Failure):
    """A failed direct fetch that remembers the HTTP status, so the caller can tell a refusal from anything else."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


class OriginUnavailable(Failure):
    """The scraping API reached the origin and the origin itself failed (HTTP 422 origin_unavailable): not retried."""


class DirectFetcher(A.PoliteFetcher):
    """PoliteFetcher whose HTTP failures carry their status. A robots.txt refusal stays a plain Failure (no fallback)."""

    def __call__(self, url, tries=3):
        try:
            return super().__call__(url, tries)
        except FetchError:
            raise
        except Failure as e:
            m = re.match(r'HTTP (\d{3}) from ', str(e))
            if m:
                raise FetchError(str(e), int(m.group(1)))
            raise


def needs_fallback(err):
    if isinstance(err, A.RobotsUnreadable):
        return True  # the origin never answered robots.txt: our own fetch cannot tell what is allowed, the paid fetch can
    s = getattr(err, 'status', None)
    return s in (403, 429) or (s is not None and 500 <= s <= 599)


def looks_js_only(body, url):
    """A 200 HTML page with no readable content: a shell that only a browser fills in."""
    if re.search(r'\.pdf(\?|$)', url, re.I) or body[:5] == b'%PDF-':
        return False
    t = body.decode('utf-8', 'replace')
    t = re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>', ' ', t)
    text = re.sub(r'\s+', ' ', re.sub(r'(?s)<[^>]*>', ' ', t)).strip()
    return len(text) < 200 and '<table' not in t.lower()


def _post(payload, key, timeout):
    # The API's edge answers 403 to the default urllib User-Agent (every fallback call from the runner on 2026-10-22 was
    # refused unpaid); the project's own agent string is accepted.
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), method='POST',
                                 headers={'X-API-Key': key, 'Content-Type': 'application/json', 'Accept': 'application/json',
                                          'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https endpoint)
            return r.status, json.loads(r.read().decode('utf-8', 'replace') or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as e:  # noqa: BLE001 (timeout, reset, DNS: reported as a failed fallback, never an escaping exception)
        return 0, {'error': type(e).__name__}


def _content(resp):
    return resp.get('content') if isinstance(resp.get('content'), dict) else {}


def _html_of(resp):
    v = _content(resp).get('html')
    return v.encode('utf-8') if isinstance(v, str) and v.strip() else b''


def _text_of(resp):
    v = _content(resp).get('text')
    return v.encode('utf-8') if isinstance(v, str) and v.strip() else b''


def is_pdf(url):
    return bool(re.search(r'\.pdf(\?|$)', url, re.I)) or 'filedownload' in url


WAYBACK = 'https://web.archive.org/web/0id_/'  # id_ = the original bytes, unmodified


class FallbackFetcher:
    """Callable url -> bytes, like PoliteFetcher. `info[url]` says how each URL was fetched; `stats()` feeds the run summary."""

    def __init__(self, direct=None, env=None, post=_post, out=sys.stderr):
        env = os.environ if env is None else env
        self.direct = direct or DirectFetcher()
        self._key = env.get(KEY_ENV, '').strip()
        try:
            self.max_usd = float(env.get(MAX_ENV) or DEFAULT_MAX_USD)
        except ValueError:
            self.max_usd = DEFAULT_MAX_USD
        self.post = post
        self.info, self.count, self.spent, self.ceiling_hit, self.errors = {}, 0, 0.0, False, []
        if not self._key:
            print(NOT_CONFIGURED, file=out)

    @property
    def configured(self):
        return bool(self._key)

    def stats(self):
        return {'configured': self.configured, 'count': self.count, 'cost_usd': round(self.spent, 6), 'max_usd': self.max_usd,
                'ceiling_reached': self.ceiling_hit, 'errors': list(self.errors)}

    def __call__(self, url):
        try:
            body = self.direct(url)
        except Failure as e:
            if not (self.configured and needs_fallback(e)):
                raise
            body = self._wayback(url) if is_pdf(url) else None
            if body is None:
                body = self._scrape(url, str(e))
        else:
            if self.configured and looks_js_only(body, url):
                body = self._scrape(url, 'direct page needs JavaScript', keep=body)
            else:
                self.info[url] = {'fetch_method': 'direct', 'fetch_tier': '', 'fetch_cost_usd': ''}
        return body

    def rescrape(self, url, why):
        """Fetch through the paid API although the direct fetch answered 200: for a body that lacks the structure the adapter expects.
        Raises Failure when no key is configured or the API fails."""
        if not self.configured:
            raise Failure('fallback fetcher: not configured')
        return self._scrape(url, why)

    def _wayback(self, url):
        """Verbatim bytes of a refused PDF from the Internet Archive, free; None when it has no copy."""
        try:
            body = self.direct(WAYBACK + url)
        except Failure:
            return None
        if body[:5] != b'%PDF-':
            return None
        self.info[url] = {'fetch_method': 'wayback', 'fetch_tier': '', 'fetch_cost_usd': ''}
        return body

    def _scrape(self, url, why, keep=None):
        if self.spent >= self.max_usd:
            self.ceiling_hit = True
            msg = 'fallback ceiling USD %.4f reached; not used for %s' % (self.max_usd, url)
            self.errors.append(msg)
            if keep is not None:
                self.info[url] = {'fetch_method': 'direct', 'fetch_tier': '', 'fetch_cost_usd': ''}
                return keep
            raise Failure('%s (%s)' % (msg, why))
        pdf = is_pdf(url)
        payload = {'url': url, 'mode': 'pdf' if pdf else 'auto', 'formats': ['text'] if pdf else ['html'], 'include_raw_html': not pdf, 'sync': True, 'timeout': 90,
                   'cost_controls': {'max_tier': '4', 'max_credits': 0.01, 'fail_fast': True}}
        status, resp = self.post(payload, self._key, 120)
        code = str(resp.get('code') or resp.get('error') or '')[:60] if isinstance(resp, dict) else ''
        if status == 422 and 'origin_unavailable' in json.dumps(resp):
            self.errors.append('origin_unavailable: %s' % url)
            raise OriginUnavailable('%s: the origin itself failed (origin_unavailable); not retried' % url)
        if status != 200:
            self.errors.append('fallback HTTP %s for %s' % (status, url))
            if keep is not None:
                self.info[url] = {'fetch_method': 'direct', 'fetch_tier': '', 'fetch_cost_usd': ''}
                return keep
            raise Failure('fallback fetch failed for %s: HTTP %s %s (direct: %s)' % (url, status, code or '', why))
        b = resp.get('billing') or {}
        cost = (b['final_cost_microcents'] / 1e8) if isinstance(b.get('final_cost_microcents'), (int, float)) else (b.get('total_credits') or 0) / 1e6
        self.count += 1
        self.spent += cost
        body = _text_of(resp) if pdf else _html_of(resp)
        if not body.strip():
            self.errors.append('fallback returned no content for %s' % url)
            raise Failure('fallback returned no content for %s' % url)
        self.info[url] = {'fetch_method': 'alterlab_text' if pdf else 'alterlab', 'fetch_tier': str(b.get('tier_used', '')), 'fetch_cost_usd': '%.6f' % cost}
        return body
