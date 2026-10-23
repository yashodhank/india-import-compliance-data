"""Unit tests for the shared adapter helpers: status words, polite fetching (robots.txt, delay, timeout), the per-list diff."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pipeline.adapters as A  # noqa: E402
import pipeline.refresh_diff as rd  # noqa: E402
from testkit import REPO  # noqa: E402


class StatusTest(unittest.TestCase):
    def test_a_denotified_section_is_denotified(self):
        self.assertEqual(('de-notified', ''), A.status_of('Food & Related Products De-notified from compulsory BIS certification', 'GSR 759(E)'))

    def test_withdrawal_carries_the_printed_date(self):
        st, tag = A.status_of('', 'Aluminium (Quality Control) Order, 2023 Withdrawal of the Order vide S.O. 5000(E) dated 13 November, 2025')
        self.assertEqual('withdrawn', st)
        self.assertEqual(' | Status: withdrawn 13 November, 2025', tag)

    def test_rescind_is_withdrawn_with_the_printed_date(self):
        st, tag = A.status_of('', 'Flux Cored Solder Wire (Quality Control) Order, 2023 S.O. 4092(E), dated 18th September 2023 Rescind Flux Cored Solder Wire Order, 2023 S.O. 165(E) Dated 12 January, 2026')
        self.assertEqual(('withdrawn', ' | Status: rescinded 12 January, 2026'), (st, tag))

    def test_a_rescinded_order_that_the_same_row_replaces_is_live(self):
        """Footwear: the 2020 order was rescinded on 3 June 2022 and the same row lists the fresh 2022 order and amendments to 2026. The last order decides."""
        text = ('Footwear (Quality Control) Order, 2020 (S.O. 3858(E) 27/10/2020) Rescind order for the Footwear (Quality Control) Order, 2020 (S.O. 2597(E), dated 3rd June 2022) '
                'Footwear (Quality Control) Order, 2022 (S.O. 2599(E), dated 3rd June 2022) Footwear (Quality Control) Amendment Order, 2026 (S.O. 3100(E), dated 12 June 2026)')
        self.assertEqual(('active', ''), A.status_of('', text))

    def test_the_chronologically_last_order_on_the_row_decides(self):
        self.assertEqual(('active', ''), A.status_of('', 'Rescinded 3 June 2022. Order, 2022 S.O. 1234 dated 4 June 2022.'))
        self.assertEqual(('withdrawn', ' | Status: rescinded 1 January 2027'), A.status_of('', 'Order, 2022 S.O. 1234 dated 4 June 2022. Rescinded 1 January 2027.'))

    def test_rescind_without_a_date_says_so(self):
        self.assertEqual(('withdrawn', ' | Status: rescinded (no date printed)'), A.status_of('', 'Order, 2021 Rescind order'))

    def test_an_order_replaced_by_a_fresh_notification_stays_active(self):
        self.assertEqual(('active', ''), A.status_of('', 'Ductile Iron Pipes Order, 2009 The above order was rescinded by DIPP vide Gazette Notification 2681(E) and a fresh Notification No. 2749(E) was issued.'))

    def test_an_ordinary_text_is_active(self):
        self.assertEqual(('active', ''), A.status_of('Cement', 'Cement (Quality Control) Order, 2003 S.O. 191(E) Dt. 17 Feb 2003'))

    def test_the_register_ignores_the_status_tag(self):
        src = open(os.path.join(REPO, 'pipeline', 'qco_register.py'), encoding='utf-8').read()
        self.assertGreaterEqual(src.count("split(' | Status:')"), 3)

class PoliteFetcherTest(unittest.TestCase):
    def fetcher(self, responses, delay=2.0):
        calls, naps = [], []
        t = [0.0]

        def opener(url, timeout=60):
            calls.append(url)
            r = responses.get(url)
            if r is None:
                import urllib.error
                raise urllib.error.HTTPError(url, 404, 'not found', {}, None)
            return r

        def sleep(n):
            naps.append(n)
            t[0] += n

        return A.PoliteFetcher(delay=delay, sleep=sleep, opener=opener, clock=lambda: t[0]), calls, naps

    def test_a_disallow_is_a_refusal_and_the_page_is_not_requested(self):
        f, calls, _ = self.fetcher({'https://h.example/robots.txt': (200, 'text/plain', b'User-agent: *\nDisallow: /\n')})
        with self.assertRaisesRegex(A.Failure, 'robots.txt disallows'):
            f('https://h.example/uploads/x.pdf')
        self.assertEqual(['https://h.example/robots.txt'], calls)

    def test_no_robots_file_or_an_error_page_means_no_rules(self):
        for robots in (None, (404, 'text/html', b'<html>Not found</html>'), (200, 'text/html', b'<html><body>Disallow: /</body></html>')):
            resp = {'https://h.example/a': (200, 'text/html', b'<p>ok</p>')}
            if robots:
                resp['https://h.example/robots.txt'] = robots
            f, _, _ = self.fetcher(resp)
            self.assertEqual(b'<p>ok</p>', f('https://h.example/a'))

    def test_a_4xx_on_robots_means_no_rules_but_a_5xx_means_nothing_is_fetched(self):
        """RFC 9309: an unavailable (4xx) robots.txt is unrestricted. The TEC host answers its robots.txt 403 to datacenter addresses."""
        for code in (401, 403, 429):
            f, calls, _ = self.fetcher({'https://h.example/robots.txt': (code, 'text/html', b'denied'), 'https://h.example/a': (200, 'x', b'ok')})
            import urllib.error as ue
            orig = f.opener

            def opener(url, orig=orig, code=code):
                if url.endswith('/robots.txt'):
                    raise ue.HTTPError(url, code, 'no', {}, None)
                return orig(url)
            f.opener = opener
            self.assertEqual(b'ok', f('https://h.example/a'))
        f, _, _ = self.fetcher({'https://h.example/robots.txt': (503, 'text/html', b'down')})
        f.opener = lambda url: (_ for _ in ()).throw(ue.HTTPError(url, 503, 'x', {}, None))
        with self.assertRaisesRegex(A.Failure, 'answered HTTP 503'):
            f('https://h.example/a')

    def test_a_page_403_after_an_open_robots_carries_its_status_so_the_paid_fallback_can_act(self):
        from pipeline import fallback as FB
        import urllib.error as ue

        def opener(url):
            raise ue.HTTPError(url, 403 if not url.endswith('/robots.txt') else 404, 'x', {}, None)
        f = FB.DirectFetcher(delay=0, sleep=lambda n: None, opener=opener)
        with self.assertRaises(FB.FetchError) as cm:
            f('https://h.example/a')
        self.assertTrue(FB.needs_fallback(cm.exception))

    def test_only_the_named_path_is_disallowed(self):
        f, _, _ = self.fetcher({'https://h.example/robots.txt': (200, 'text/plain', b'User-agent: *\nDisallow: /wp-admin/\n'), 'https://h.example/lists/': (200, 'text/html', b'x')})
        self.assertEqual(b'x', f('https://h.example/lists/'))

    def test_two_seconds_between_requests_to_one_host(self):
        f, calls, naps = self.fetcher({'https://h.example/a': (200, 'x', b'1'), 'https://h.example/b': (200, 'x', b'2')})
        f('https://h.example/a')
        f('https://h.example/b')
        self.assertGreaterEqual(len(naps), 2)
        self.assertTrue(all(abs(n - 2.0) < 1e-9 or n < 2.0 for n in naps))

    def test_a_non_200_and_an_empty_body_are_failures(self):
        f, _, _ = self.fetcher({'https://h.example/a': (500, 'x', b'oops'), 'https://h.example/b': (200, 'x', b'  ')})
        with self.assertRaisesRegex(A.Failure, 'HTTP 500'):
            f('https://h.example/a')
        with self.assertRaisesRegex(A.Failure, 'empty body'):
            f('https://h.example/b')


class DiffTest(unittest.TestCase):
    def rows(self):
        base = {'scheme': 'S', 'authority': 'A', 'group': 'G', 'source_url': 'u', 'retrieved_on': '2026-10-01', 'status': 'active'}
        return [dict(base, product_name='Alpha', is_codes='IS 1', notes='QCO dated 01 January 2020'), dict(base, product_name='Beta', is_codes='IS 2', notes='n'),
                dict(base, product_name='Gamma', is_codes='IS 3', notes='n')]

    def test_added_removed_status_and_date_changes_are_counted_on_code_and_name(self):
        before = self.rows()
        after = [dict(r) for r in before]
        after[0]['notes'] = 'QCO dated 01 January 2020 Amendment dated 5 May 2026'
        after[1]['status'] = 'withdrawn'
        after.pop(2)
        after.append(dict(before[0], product_name='Delta', is_codes='IS 4', notes='n'))
        d = rd.list_diff(before, after)
        self.assertEqual((1, 1, 1, 1), (d['added'], d['removed'], d['status_changed'], d['date_changed']))
        self.assertEqual([{'row': 'Beta (IS 2)', 'from': 'active', 'to': 'withdrawn'}], d['status_sample'])
        self.assertEqual('2020-01-01', d['date_sample'][0]['from'])
        self.assertEqual('2020-01-01 ; 2026-05-05', d['date_sample'][0]['to'])

    def test_retrieved_on_alone_is_no_change_and_the_markdown_says_so(self):
        before = self.rows()
        after = [dict(r, retrieved_on='2026-10-22') for r in before]
        d = rd.list_diff(before, after)
        self.assertEqual(0, d['added'] + d['removed'] + d['status_changed'] + d['date_changed'] + d['other_changed'])
        self.assertFalse(rd.changed(d))

    def test_the_same_key_twice_is_told_apart_by_order(self):
        r = self.rows()[0]
        d = rd.list_diff([r, dict(r)], [r])
        self.assertEqual(1, d['removed'])



class ReviewStatusTest(unittest.TestCase):
    def test_case_and_the_past_tense_do_not_hide_a_withdrawal(self):
        self.assertEqual('withdrawn', A.status_of('', 'withdrawal of the Order dated 13 November 2025')[0])
        self.assertEqual('withdrawn', A.status_of('', 'Rescinded vide S.O. 1(E) 12 January 2026')[0])
        self.assertEqual('withdrawn', A.status_of('', 'WITHDRAWAL OF the order')[0])

    def test_a_replaced_order_still_stays_active(self):
        self.assertEqual('active', A.status_of('', 'The above order was rescinded by DIPP and a fresh Notification was issued.')[0])


class ReviewFetcherTest(unittest.TestCase):
    def make(self, responses, delay=2.0, slow=0.0):
        import urllib.error
        calls, naps, t = [], [], [0.0]

        def opener(url, timeout=60):
            calls.append(url)
            t[0] += slow
            r = responses.get(url)
            if isinstance(r, Exception):
                raise r
            if r is None:
                raise urllib.error.HTTPError(url, 404, 'nf', {}, None)
            return r

        def sleep(n):
            naps.append(n)
            t[0] += n

        return A.PoliteFetcher(delay=delay, sleep=sleep, opener=opener, clock=lambda: t[0]), calls, naps

    def test_the_nap_is_exactly_the_delay_between_two_requests_to_one_host(self):
        f, _, naps = self.make({'https://h.example/a': (200, 'x', b'1'), 'https://h.example/b': (200, 'x', b'2')})
        f('https://h.example/a')
        f('https://h.example/b')
        self.assertEqual([2.0, 2.0], naps[-2:])

    def test_a_slow_response_does_not_cancel_the_next_wait(self):
        f, _, naps = self.make({'https://h.example/a': (200, 'x', b'1'), 'https://h.example/b': (200, 'x', b'2')}, slow=3.0)
        f('https://h.example/a')
        before = len(naps)
        f('https://h.example/b')
        self.assertEqual([2.0], naps[before:])

    def test_a_robots_transport_error_or_a_server_error_is_a_refusal(self):
        import urllib.error
        for err in (urllib.error.HTTPError('https://h.example/robots.txt', 503, 'unavailable', {}, None), urllib.error.HTTPError('https://h.example/robots.txt', 500, 'x', {}, None), OSError('reset')):
            f, calls, _ = self.make({'https://h.example/robots.txt': err, 'https://h.example/a': (200, 'x', b'1')})
            with self.assertRaises(A.Failure):
                f('https://h.example/a')
            self.assertNotIn('https://h.example/a', calls)

    def test_a_missing_robots_file_is_no_rules(self):
        f, _, _ = self.make({'https://h.example/a': (200, 'x', b'1')})
        self.assertEqual(b'1', f('https://h.example/a'))

    def test_star_disallow_wins_over_an_earlier_mozilla_allow(self):
        body = b'User-agent: Mozilla\nAllow: /\n\nUser-agent: *\nDisallow: /\n'
        f, calls, _ = self.make({'https://h.example/robots.txt': (200, 'text/plain', body), 'https://h.example/a': (200, 'x', b'1')})
        with self.assertRaisesRegex(A.Failure, 'robots.txt disallows'):
            f('https://h.example/a')
        self.assertNotIn('https://h.example/a', calls)

    def test_cpcb_robots_as_published_refuses_the_uploads_path(self):
        body = b'User-Agent: *\nAllow: /web/\nDisallow: /\n'
        f, _, _ = self.make({'https://cpcb.example/robots.txt': (200, 'text/plain', body)})
        with self.assertRaisesRegex(A.Failure, 'robots.txt disallows'):
            f('https://cpcb.example/uploads/Projects/E-Waste/rules.pdf')

    def test_a_page_that_answers_is_requested_once(self):
        f, calls, _ = self.make({'https://h.example/a': (200, 'x', b'1')})
        f('https://h.example/a')
        self.assertEqual(1, calls.count('https://h.example/a'))

    def test_a_transport_error_is_retried_and_then_succeeds(self):
        n = [0]
        f, calls, _ = self.make({})

        def flaky(url, timeout=60):
            calls.append(url)
            n[0] += 1
            if n[0] == 2:  # first call is robots.txt
                raise OSError('reset')
            if url.endswith('robots.txt'):
                import urllib.error
                raise urllib.error.HTTPError(url, 404, 'nf', {}, None)
            return 200, 'x', b'ok'
        f.opener = flaky
        self.assertEqual(b'ok', f('https://h.example/a'))
        self.assertEqual(2, calls.count('https://h.example/a'))

    def test_the_default_fetcher_passes_its_timeout_on(self):
        seen = []
        f = A.PoliteFetcher(sleep=lambda n: None, timeout=45, urlopen=lambda req, timeout: seen.append(timeout) or _Resp())
        f('https://h.example/robots.txt')
        self.assertEqual({45}, set(seen))


class _Resp:
    status = 200
    headers = {'Content-Type': 'text/plain'}

    def read(self, n):
        return b'x'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ReviewDiffTest(unittest.TestCase):
    def test_deleting_the_middle_of_three_repeated_keys_is_one_removal_of_that_serial(self):
        base = {'scheme': 'S', 'authority': 'A', 'group': 'G', 'source_url': 'u', 'retrieved_on': 'x', 'status': 'active', 'product_name': 'Breaker', 'is_codes': 'IS 1'}
        before = [dict(base, notes='Sr 1.1(a) | t'), dict(base, notes='Sr 1.1(b) | t'), dict(base, notes='Sr 1.1(c) | t')]
        after = [before[0], before[2]]
        d = rd.list_diff(before, after)
        self.assertEqual((0, 1, 0, 0, 0), (d['added'], d['removed'], d['status_changed'], d['date_changed'], d['other_changed']))
        self.assertIn('1.1(b)', d['removed_sample'][0])

    def test_the_same_appliance_on_two_schemes_is_two_keys(self):
        base = {'authority': 'A', 'group': 'G', 'source_url': 'u', 'retrieved_on': 'x', 'status': 'active', 'product_name': 'Induction Hob', 'is_codes': '', 'notes': 'n'}
        before = [dict(base, scheme='M'), dict(base, scheme='V')]
        d = rd.list_diff(before, [dict(base, scheme='V', status='withdrawn'), dict(base, scheme='M')])
        self.assertEqual((0, 0, 1), (d['added'], d['removed'], d['status_changed']))
