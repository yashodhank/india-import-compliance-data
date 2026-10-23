"""Fallback fetcher and change detector, with a stubbed HTTP layer. Nothing here touches the network."""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from pipeline import fallback as FB  # noqa: E402
from pipeline import monitor as M  # noqa: E402

URL = 'https://example.org/list'
PAGE = b'<html><body><table><tr><td>row</td></tr></table>' + b'x' * 300 + b'</body></html>'


class Direct:
    """Stands in for the polite direct fetcher."""

    def __init__(self, result):
        self.result, self.calls = result, []

    def __call__(self, url):
        self.calls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Api:
    def __init__(self, status=200, resp=None):
        self.status, self.calls = status, []
        self.resp = resp if resp is not None else {'content': {'html': '<html>from api</html>'}, 'billing': {'tier_used': '3', 'final_cost_microcents': 40000}}

    def __call__(self, payload, key, timeout):
        self.calls.append((payload, key))
        return self.status, self.resp


def make(direct, api, key='k-test'):
    env = {'ALTERLAB_API_KEY': key} if key else {}
    out = io.StringIO()
    return FB.FallbackFetcher(direct=direct, env=env, post=api, out=out), out


class FallbackTest(unittest.TestCase):
    def test_direct_success_makes_no_api_call(self):
        api = Api()
        f, _ = make(Direct(PAGE), api)
        self.assertEqual(PAGE, f(URL))
        self.assertEqual([], api.calls)
        self.assertEqual('direct', f.info[URL]['fetch_method'])

    def test_a_403_uses_the_fallback_and_records_it(self):
        api = Api()
        f, _ = make(Direct(FB.FetchError('HTTP 403 from ' + URL, 403)), api)
        self.assertEqual(b'<html>from api</html>', f(URL))
        payload = api.calls[0][0]
        self.assertEqual(('auto', ['html'], True, True), (payload['mode'], payload['formats'], payload['include_raw_html'], payload['sync']))
        self.assertEqual({'max_tier': '4', 'max_credits': 0.01, 'fail_fast': True}, payload['cost_controls'])
        self.assertEqual({'fetch_method': 'alterlab', 'fetch_tier': '3', 'fetch_cost_usd': '0.000400'}, f.info[URL])
        self.assertEqual((1, 0.0004), (f.stats()['count'], f.stats()['cost_usd']))

    def test_a_pdf_asks_for_pdf_mode(self):
        api = Api(resp={'content': {'text': 'extracted', 'html': ''}, 'billing': {'tier_used': '1', 'final_cost_microcents': 200}})
        f, _ = make(Direct(FB.FetchError('HTTP 429 from x', 429)), api)
        f('https://example.org/a.pdf')
        self.assertEqual(('pdf', ['text']), (api.calls[0][0]['mode'], api.calls[0][0]['formats']))
        self.assertEqual('alterlab_text', f.info['https://example.org/a.pdf']['fetch_method'])

    def test_origin_unavailable_is_a_recorded_failure_without_retry(self):
        api = Api(422, {'error': 'origin_unavailable'})
        f, _ = make(Direct(FB.FetchError('HTTP 503 from ' + URL, 503)), api)
        with self.assertRaises(FB.OriginUnavailable):
            f(URL)
        self.assertEqual(1, len(api.calls))
        self.assertEqual(0, f.stats()['count'])
        self.assertTrue(any('origin_unavailable' in e for e in f.stats()['errors']))

    def test_a_missing_key_makes_no_call_and_says_so_once(self):
        api = Api()
        f, out = make(Direct(FB.FetchError('HTTP 403 from ' + URL, 403)), api, key='')
        for _ in range(2):
            with self.assertRaises(FB.Failure):
                f(URL)
        self.assertEqual([], api.calls)
        self.assertEqual('fallback fetcher: not configured\n', out.getvalue())

    def test_the_paid_api_request_carries_the_project_user_agent_and_never_urllibs_default(self):
        """2026-10-22: the API edge answered 403 to urllib's default agent, so every runner fallback was refused unpaid."""
        import unittest.mock as mock

        sent = []

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{}'

        def opener(req, timeout=None):
            sent.append(req)
            return Resp()

        with mock.patch.object(FB.urllib.request, 'urlopen', opener):
            FB._post({'url': URL}, 'k-test', 5)
        self.assertEqual(1, len(sent))
        self.assertEqual(FB.USER_AGENT, sent[0].get_header('User-agent'))
        self.assertIn('github.com/yashodhank/india-import-compliance-data', sent[0].get_header('User-agent'))
        self.assertNotIn('Python-urllib', sent[0].get_header('User-agent'))

    def test_a_robots_refusal_reaches_neither_route(self):
        api = Api()
        f, _ = make(Direct(FB.Failure('robots.txt disallows ' + URL)), api)
        with self.assertRaises(FB.Failure):
            f(URL)
        self.assertEqual([], api.calls)

    def test_the_real_direct_fetcher_checks_robots_before_any_get(self):
        seen = []

        def opener(url):
            seen.append(url)
            return 200, 'text/plain', b'User-agent: *\nDisallow: /\n'
        api = Api()
        f = FB.FallbackFetcher(direct=FB.DirectFetcher(delay=0, sleep=lambda s: None, opener=opener), env={'ALTERLAB_API_KEY': 'k'}, post=api, out=io.StringIO())
        with self.assertRaises(FB.Failure):
            f(URL)
        self.assertEqual(['https://example.org/robots.txt'], seen)
        self.assertEqual([], api.calls)

    def test_a_robots_dns_failure_or_timeout_is_retried_once_then_goes_to_the_paid_fallback(self):
        import urllib.error
        for exc in (urllib.error.URLError('[Errno -3] Temporary failure in name resolution'), TimeoutError('timed out')):
            seen, naps = [], []

            def opener(url, exc=exc):
                seen.append(url)
                raise exc
            api = Api()
            f = FB.FallbackFetcher(direct=FB.DirectFetcher(delay=0, sleep=naps.append, opener=opener), env={'ALTERLAB_API_KEY': 'k'}, post=api, out=io.StringIO())
            self.assertEqual(b'<html>from api</html>', f(URL))
            self.assertEqual(['https://example.org/robots.txt'] * 2, seen, 'retried once, the page itself never requested')
            self.assertIn(10.0, naps)
            self.assertEqual(1, len(api.calls))

    def test_a_robots_transport_fault_without_the_fallback_is_unchanged(self):
        def opener(url):
            raise OSError('reset')
        api = Api()
        f = FB.FallbackFetcher(direct=FB.DirectFetcher(delay=0, sleep=lambda s: None, opener=opener), env={}, post=api, out=io.StringIO())
        with self.assertRaisesRegex(FB.Failure, 'could not be read'):
            f(URL)
        self.assertEqual([], api.calls)

    def test_a_robots_5xx_is_still_a_block_and_not_sent_to_the_fallback(self):
        import urllib.error

        def opener(url):
            raise urllib.error.HTTPError(url, 503, 'x', {}, None)
        api = Api()
        f = FB.FallbackFetcher(direct=FB.DirectFetcher(delay=0, sleep=lambda s: None, opener=opener), env={'ALTERLAB_API_KEY': 'k'}, post=api, out=io.StringIO())
        with self.assertRaisesRegex(FB.Failure, 'HTTP 503'):
            f(URL)
        self.assertEqual([], api.calls)

    def test_the_run_ceiling_stops_the_fallback(self):
        api = Api(resp={'content': {'html': '<p>x</p>'}, 'billing': {'tier_used': '4', 'final_cost_microcents': 30_000_000}})
        f, _ = make(Direct(FB.FetchError('HTTP 403 from x', 403)), api)
        f.max_usd = 0.25
        f(URL)  # costs 0.30, over the ceiling
        with self.assertRaises(FB.Failure):
            f('https://example.org/two')
        self.assertEqual(1, len(api.calls))
        self.assertTrue(f.stats()['ceiling_reached'])

    def test_a_js_only_page_goes_to_the_fallback_but_a_real_page_does_not(self):
        shell = b'<html><body><noscript>enable javascript</noscript><div id=app></div><script>x()</script></body></html>'
        api = Api()
        f, _ = make(Direct(shell), api)
        self.assertEqual(b'<html>from api</html>', f(URL))
        self.assertTrue(FB.looks_js_only(shell, URL))
        self.assertFalse(FB.looks_js_only(PAGE, URL))

    def test_the_key_is_only_ever_sent_in_the_header_argument(self):
        api = Api()
        f, out = make(Direct(FB.FetchError('HTTP 403 from x', 403)), api, key='SECRET-KEY-123')
        f(URL)
        self.assertNotIn('SECRET-KEY-123', repr(api.calls[0][0]) + out.getvalue() + repr(f.stats()) + repr(f.info))


class PdfAndUrlTest(unittest.TestCase):
    def test_a_refused_pdf_prefers_wayback_bytes_over_alterlab(self):
        class D:
            def __call__(s, url):
                if url.startswith(FB.WAYBACK):
                    return b'%PDF-1.4 original'
                raise FB.FetchError('HTTP 403 from ' + url, 403)
        api = Api()
        f, _ = make(D(), api)
        self.assertEqual(b'%PDF-1.4 original', f('https://example.org/a.pdf'))
        self.assertEqual(([], 'wayback'), (api.calls, f.info['https://example.org/a.pdf']['fetch_method']))

    def test_the_fallback_gets_the_adapters_lang_en_url_for_bis_sources(self):
        from pipeline import refresh as rf
        from pipeline import sources as S
        api = Api()
        seen = []

        class D:
            def __call__(s, url):
                seen.append(url)
                raise FB.FetchError('HTTP 403 from ' + url, 403)
        f, _ = make(D(), api)
        ctx = rf.Ctx('/nonexistent', '2026-10-22', False, f, True)
        spec = next(x for x in S.LISTS if x['id'] == 'bis-scheme1')
        rf.get_raw(ctx, spec['id'], spec['url'], spec['lang'], spec['stem'], spec['ext'])
        self.assertTrue(api.calls[0][0]['url'].endswith('?lang=en'), api.calls[0][0]['url'])
        for sid, url in S.source_urls():
            if 'bis.gov.in' in url and not url.endswith('.pdf'):
                self.assertIn('lang=en', url)

    @unittest.skipUnless(os.environ.get('ALTERLAB_LIVE_SMOKE') and os.environ.get('ALTERLAB_API_KEY'), 'live smoke is opt-in')
    def test_live_smoke(self):
        st, resp = FB._post({'url': 'https://example.com', 'mode': 'auto', 'formats': ['html'], 'include_raw_html': True, 'sync': True, 'timeout': 90,
                             'cost_controls': {'max_tier': '4', 'max_credits': 0.01, 'fail_fast': True}}, os.environ['ALTERLAB_API_KEY'], 120)
        self.assertEqual(200, st)
        self.assertTrue(FB._html_of(resp))


class MonitorTest(unittest.TestCase):
    def test_volatile_fragments_do_not_count_as_change(self):
        a = b'<html><head><meta name="csrf-token" content="AAA"><script src="a.js?ver=1"></script></head><body> Copyright &copy; 2026 BEE <p>row   one</p></body></html>'
        b = b'<html><head><meta name="csrf-token" content="BBB"><script src="a.js?ver=2"></script></head><body> Copyright &copy; 2027 BEE <p>row one</p></body></html>'
        self.assertEqual(M.digest(a), M.digest(b))
        self.assertNotEqual(M.digest(a), M.digest(a.replace(b'row   one', b'row two')))

    def test_first_look_records_then_a_change_is_reported(self):
        urls = [('a', 'https://x/a'), ('b', 'https://x/b')]
        bodies = {'https://x/a': b'<p>one</p>', 'https://x/b': b'<p>two</p>'}
        st, ch, fl = M.look(lambda u: bodies[u], urls, {}, '2026-10-22')
        self.assertEqual(([], []), (ch, fl))
        bodies['https://x/b'] = b'<p>three</p>'
        st2, ch, fl = M.look(lambda u: bodies[u], urls, st, '2026-10-23')
        self.assertEqual(['b'], ch)
        self.assertEqual('2026-10-23', st2['b']['changed_on'])

    def test_an_unreachable_source_keeps_its_hash_and_is_not_a_change(self):
        st, _, _ = M.look(lambda u: b'<p>one</p>', [('a', 'https://x/a')], {}, '2026-10-22')

        def boom(u):
            raise FB.Failure('HTTP 403')
        st2, ch, fl = M.look(boom, [('a', 'https://x/a')], st, '2026-10-23')
        self.assertEqual(([], st['a']), (ch, st2['a']))
        self.assertEqual(1, len(fl))


if __name__ == '__main__':
    unittest.main()
