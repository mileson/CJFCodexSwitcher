import unittest

import codex_switcher


class AccountIdentityTests(unittest.TestCase):
    def test_same_email_different_plan_is_not_same_identity(self):
        existing = {
            "record_key": "",
            "email": "user@example.com",
            "plan_type": "plus",
        }
        candidate = {
            "record_key": "",
            "email": "USER@example.com",
            "plan_type": "team",
        }

        self.assertFalse(codex_switcher.same_account_identity(existing, candidate))

    def test_same_email_same_plan_is_same_identity(self):
        existing = {
            "record_key": "",
            "email": "user@example.com",
            "plan_type": "plus",
        }
        candidate = {
            "record_key": "",
            "email": "USER@example.com",
            "plan_type": "PLUS",
        }

        self.assertTrue(codex_switcher.same_account_identity(existing, candidate))


if __name__ == "__main__":
    unittest.main()
