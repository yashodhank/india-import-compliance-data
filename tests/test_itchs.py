"""ITC(HS) parser: text cleaning, date normalisation, per-chapter assertions, and refusal of a document that is not a chapter export."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pipeline import itchs  # noqa: E402
from pipeline.adapters import Failure  # noqa: E402


def chapter(items, notes=None, ch='03'):
    return json.dumps({'responseCode': 200, 'chapterNo': ch, 'chapterDesc': 'Fish.', 'section': 'I', 'sectionName': 'LIVE', 'notes': notes or [], 'itcCodeClassifications': items}).encode()


def item(code, desc='d', policy='Free', cond=None, no='', date=''):
    return {'itcCode': code, 'itcDescription': desc, 'impPolicy': policy, 'impCondition': cond, 'notificationNo': no, 'notificationDate': date}


class ItchsParseTest(unittest.TestCase):
    def test_text_is_stripped_of_html_and_mojibake_but_the_words_are_kept(self):
        self.assertEqual('Import permitted as per Policy Condition 2', itchs.text_of('<p>Import&nbsp;permitted as per\n Policy Condition 2</p>\n'))
        self.assertEqual('Hot roled steel', itchs.text_of('Â\xa0Hot roled steel'))
        self.assertEqual('', itchs.text_of(None))

    def test_dates(self):
        self.assertEqual('2023-05-29', itchs.iso_or_raw('29/05/2023'))
        self.assertEqual('2026-07-22', itchs.iso_or_raw('2026-07-22 00:00:00'))
        self.assertEqual('01/02/2020 , 03/04/2021', itchs.iso_or_raw('01/02/2020 , 03/04/2021'))
        self.assertEqual('', itchs.iso_or_raw(None))

    def test_condition_refs(self):
        self.assertEqual('7;3', itchs.condition_refs('Subject to Policy condition no. 07 of this chapter and Policy Condition (3)'))

    def test_levels_and_counts(self):
        rows, notes, snotes, st = itchs.parse_chapter(chapter([item('0301'), item('030191'), item('03019110', cond='<p>x</p>', no='08/2023', date='29/05/2023')]), '03', '2026-10-22')
        self.assertEqual([4, 6, 8], [r['level'] for r in rows])
        self.assertEqual((3, 3, 1), (st['items_in_export'], st['rows_parsed'], st['rows_8digit']))
        self.assertEqual('2023-05-29', rows[2]['notification_date'])

    def test_duplicate_codes_are_kept_and_reported(self):
        rows, _, _, st = itchs.parse_chapter(chapter([item('03019110'), item('03019110')]), '03', 'x')
        self.assertEqual(2, len(rows))
        self.assertEqual(['03019110'], st['duplicate_codes_in_export'])

    def test_not_a_chapter_export_is_a_failure(self):
        for body in (b'<html>maintenance</html>', json.dumps({'responseCode': 500}).encode(), chapter([item('0301')], ch='04')):
            with self.assertRaises(Failure):
                itchs.parse_chapter(body, '03', 'x')

    def test_a_malformed_code_is_a_failure_not_a_dropped_row(self):
        with self.assertRaisesRegex(Failure, 'not 4, 6 or 8 digits'):
            itchs.parse_chapter(chapter([item('0301'), item('03X1')]), '03', 'x')

    def test_notes_become_rows(self):
        notes = [{'noteName': 'Main', 'noteDetails': [{'notetype': 'Policy Condition', 'chapter': '03', 'noteSerialNo': '1', 'notes': '<p>Cond</p>', 'noteSection': 'I'}],
                  'noteSectionDetails': [{'notetype': 'Main', 'section': 'I', 'noteSerialNo': '1', 'notes': 'sec'}]}]
        _, n, s, st = itchs.parse_chapter(chapter([item('0301')], notes), '03', 'x')
        self.assertEqual(['Cond'], [x['text'] for x in n])
        self.assertEqual(['sec'], [x['text'] for x in s])
        self.assertEqual(1, st['notes_in_export'])


class DgftSessionTest(unittest.TestCase):
    def test_one_request_per_second_and_the_agent_names_the_repository(self):
        from pipeline.adapters import USER_AGENT
        self.assertIn('github.com/yashodhank/india-import-compliance-data', USER_AGENT)
        naps, t = [], [0.0]

        def sleep(n):
            naps.append(n)
            t[0] += n
        s = itchs.DgftSession(sleep=sleep, clock=lambda: t[0])
        s._wait()
        s._wait()
        self.assertEqual([1.0], naps)

    def test_listing_parser(self):
        html = b'<a class="itchsimport" data-chapterId="02">x</a><a class="itchsimport" data-chapterId="01">y</a>'
        self.assertEqual(['01', '02'], itchs.chapters_in_listing(html))
        with self.assertRaises(Failure):
            itchs.chapters_in_listing(b'<html></html>')
