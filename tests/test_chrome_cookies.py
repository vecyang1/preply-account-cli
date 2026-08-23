import hashlib
import unittest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from preply_cli import chrome_cookies as C


def _encrypt_v10(value: str, key: bytes, host: str, prepend_hash: bool) -> bytes:
    """Reproduce Chrome's v10 cookie encryption for round-trip testing."""
    plaintext = value.encode("utf-8")
    if prepend_hash:
        plaintext = hashlib.sha256(host.encode()).digest() + plaintext
    pad = 16 - (len(plaintext) % 16)
    plaintext += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + enc.update(plaintext) + enc.finalize()


class DecryptV10Test(unittest.TestCase):
    KEY = hashlib.pbkdf2_hmac("sha1", b"testpw", b"saltysalt", 1003, dklen=16)
    HOST = "preply.com"

    def test_roundtrip_with_host_hash_prefix(self):
        blob = _encrypt_v10("abc123session", self.KEY, self.HOST, prepend_hash=True)
        self.assertEqual(C._decrypt_v10(blob, self.KEY, self.HOST), "abc123session")

    def test_roundtrip_without_host_hash_prefix(self):
        blob = _encrypt_v10("legacyvalue", self.KEY, self.HOST, prepend_hash=False)
        self.assertEqual(C._decrypt_v10(blob, self.KEY, self.HOST), "legacyvalue")

    def test_rejects_non_v10(self):
        with self.assertRaises(C.ChromeCookieError):
            C._decrypt_v10(b"v20garbage", self.KEY, self.HOST)


class ProfileCookiesReprTest(unittest.TestCase):
    def test_repr_hides_secret_values(self):
        pc = C.ProfileCookies(profile="Default", sessionid="SECRET_SID",
                              csrftoken="SECRET_CSRF", sessionid_expiry_webkit=1)
        text = repr(pc)
        self.assertIn("Default", text)
        self.assertNotIn("SECRET_SID", text)
        self.assertNotIn("SECRET_CSRF", text)


class WebkitTimeTest(unittest.TestCase):
    def test_zero_is_none(self):
        self.assertIsNone(C.webkit_to_iso(0))
        self.assertIsNone(C.webkit_to_iso(None))

    def test_known_value(self):
        # 13300000000000000 us after 1601-01-01 → a valid ISO string in 2022.
        iso = C.webkit_to_iso(13300000000000000)
        self.assertTrue(iso.startswith("2022-"))


if __name__ == "__main__":
    unittest.main()
