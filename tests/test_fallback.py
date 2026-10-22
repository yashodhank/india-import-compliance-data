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
        self.resp = resp if resp is not None else {'raw_html': '<html>from api</html>', 'billing': {'tier_used': '3', 'final_cost_microcents': 40000}}

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
        api = Api()
        f, _ = make(Direct(FB.FetchError('HTTP 429 from x', 429)), api)
        f('https://example.org/a.pdf')
        self.assertEqual('pdf', api.calls[0][0]['mode'])

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

    def test_the_run_ceiling_stops_the_fallback(self):
        api = Api(resp={'raw_html': '<p>x</p>', 'billing': {'tier_used': '4', 'final_cost_microcents': 30_000_000}})
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
