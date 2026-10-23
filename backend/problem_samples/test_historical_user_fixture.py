"""Fixture normalization tests. Runnable without Django or PostgreSQL."""
import copy
import unittest

from problem_samples.historical_user_fixture import (
    HistoricalUserFixtureError, normalize_user_keys,
)


class HistoricalUserFixtureTests(unittest.TestCase):
    fields = {('accounts.userprofile', 'user'), ('problem_samples.problemsample', 'created_by')}

    def fixture(self):
        return [
            {'model': 'auth.user', 'fields': {'username': 'first', 'password': 'hashed1'}},
            {'model': 'auth.user', 'fields': {'username': 'second', 'password': 'hashed2'}},
            {'model': 'accounts.userprofile', 'pk': 42, 'fields': {'user': ['first'], 'role': 'lab'}},
            {'model': 'problem_samples.problemsample', 'pk': 'ticket', 'fields': {
                'created_by': ['second'], 'custom_values': {'names': ['first', 'second']}}},
        ]

    def test_assigns_numeric_pks_and_rewrites_only_relations(self):
        original = self.fixture()
        out, stats = normalize_user_keys(copy.deepcopy(original), fk_fields=self.fields)
        self.assertEqual([x['pk'] for x in out[:2]], [1, 2])
        self.assertEqual(out[2]['fields']['user'], 1)
        self.assertEqual(out[3]['fields']['created_by'], 2)
        self.assertEqual(out[3]['fields']['custom_values']['names'], ['first', 'second'])
        self.assertEqual([x['fields']['password'] for x in out[:2]], ['hashed1', 'hashed2'])
        self.assertEqual(stats, {'users_assigned_ids': 2, 'user_relations_normalized': 2})

    def test_preserves_existing_primary_keys(self):
        src = self.fixture()
        src[0]['pk'] = 17
        out, _ = normalize_user_keys(src, fk_fields=self.fields)
        self.assertEqual([r['pk'] for r in out[:2]], [17, 18])
        self.assertEqual(out[2]['fields']['user'], 17)

    def test_rejects_missing_referenced_user(self):
        src = self.fixture()
        src[2]['fields']['user'] = ['missing']
        with self.assertRaises(HistoricalUserFixtureError):
            normalize_user_keys(src, fk_fields=self.fields)

    def test_rejects_duplicate_usernames(self):
        src = self.fixture()
        src[1]['fields']['username'] = 'first'
        with self.assertRaises(HistoricalUserFixtureError):
            normalize_user_keys(src, fk_fields=self.fields)

    def test_rejects_duplicate_primary_keys(self):
        src = self.fixture()
        src[0]['pk'] = 2
        src[1]['pk'] = 2
        with self.assertRaises(HistoricalUserFixtureError):
            normalize_user_keys(src, fk_fields=self.fields)

    def test_rejects_malformed_relationship(self):
        src = self.fixture()
        src[2]['fields']['user'] = ['first', 'second']
        with self.assertRaises(HistoricalUserFixtureError):
            normalize_user_keys(src, fk_fields=self.fields)

    def test_many_to_many_user_relations(self):
        src = self.fixture()
        src[3]['fields']['reviewers'] = [['first'], ['second']]
        out, stats = normalize_user_keys(src, fk_fields=self.fields,
            m2m_fields={('problem_samples.problemsample', 'reviewers')})
        self.assertEqual(out[3]['fields']['reviewers'], [1, 2])
        self.assertEqual(stats['user_relations_normalized'], 4)


if __name__ == '__main__':
    unittest.main()
