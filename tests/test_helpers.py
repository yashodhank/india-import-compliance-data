"""Unit tests for the shared adapter helpers: status words, polite fetching (robots.txt, delay), the per-list diff."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pipeline.adapters as A  # noqa: E402
import pipeline.refresh_diff as rd  # noqa: E402
from testkit import REPO, TODAY  # noqa: E402


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
                raise OSError('not found')
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

