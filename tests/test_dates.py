"""Compact public date labels retain every date and its precision."""
import unittest

from app import date_label


class DateLabelTests(unittest.TestCase):
    def test_shared_months_and_years_are_omitted_without_losing_days(self):
        cases = {
            '2026-10': 'Ottobre 2026',
            '2026-10-06': '6 ottobre 2026',
            '2026-10-06, 2026-10-07': '6 - 7 ottobre 2026',
            '2026-10-06, 2026-11-07': '6 ottobre - 7 novembre 2026',
            '2026-10-06, 2026-11-06': '6 ottobre - 6 novembre 2026',
            '2026-12-31, 2027-01-02': '31 dicembre 2026 - 2 gennaio 2027',
            '2026-10-06, 2027-10-06': '6 ottobre 2026 - 6 ottobre 2027',
            '2026-10-01, 2026-10-03, 2026-10-08': '1 - 3 - 8 ottobre 2026',
            '2026-10-01, 2026-10-03, 2026-11-08': '1 - 3 ottobre - 8 novembre 2026',
            '2026-12-30, 2026-12-31, 2027-01-01, 2027-01-02': '30 - 31 dicembre 2026 - 1 - 2 gennaio 2027',
            '2026-10, 2026-11': 'Ottobre - novembre 2026',
            '2026-12, 2027-01': 'Dicembre 2026 - gennaio 2027',
            '2026-10, 2026-11-06': 'Ottobre - 6 novembre 2026',
            '2026-10, 2026-10-06': 'Ottobre - 6 ottobre 2026',
            '2026-10-06, 2026-11': '6 ottobre - novembre 2026',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(date_label(value), expected)
