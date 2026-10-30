"""비밀번호 해싱을 검증합니다. 외부 라이브러리 없이 표준 scrypt만 씁니다."""

import unittest

from app.passwords import (
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    hash_password,
    validate_password,
    verify_password,
)

PASSWORD = "correct horse battery"


class PasswordTests(unittest.TestCase):
    def test_hash_verifies_and_rejects(self):
        stored = hash_password(PASSWORD)
        self.assertTrue(verify_password(PASSWORD, stored))
        self.assertFalse(verify_password(PASSWORD + "x", stored))
        self.assertFalse(verify_password("", stored))

    def test_same_password_gets_different_hash(self):
        # 소금이 매번 달라야 같은 비밀번호를 쓴 계정이 드러나지 않습니다.
        self.assertNotEqual(hash_password(PASSWORD), hash_password(PASSWORD))

    def test_stored_format_carries_parameters(self):
        prefix, n, r, p, salt, digest = hash_password(PASSWORD).split("$")
        self.assertEqual(prefix, "scrypt")
        self.assertEqual((int(n), int(r), int(p)), (2**14, 8, 1))
        self.assertTrue(salt and digest)

    def test_broken_stored_value_is_false_not_error(self):
        for stored in ("", None, "garbage", "scrypt$x$8$1$aa$bb", "bcrypt$1$1$1$aa$bb"):
            self.assertFalse(verify_password(PASSWORD, stored))

    def test_short_password_is_rejected(self):
        with self.assertRaises(PasswordPolicyError):
            validate_password("a" * (MIN_PASSWORD_LENGTH - 1))
        with self.assertRaises(PasswordPolicyError):
            hash_password("short")

    def test_very_long_password_is_rejected(self):
        # scrypt는 길이 제한이 없어 거대한 입력이 그대로 CPU를 먹습니다.
        with self.assertRaises(PasswordPolicyError):
            validate_password("a" * 1000)


if __name__ == "__main__":
    unittest.main()
