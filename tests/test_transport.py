import os
import unittest
from unittest import mock

from preply_cli.transport import (
    PreplyTransportError,
    _is_cloudflare_challenge,
    _parse_graphql_payload,
    mask_proxy,
    resolve_proxy_url,
)


class TransportProxyResolutionTests(unittest.TestCase):
    def test_explicit_argument_wins_over_environment(self):
        with mock.patch.dict(os.environ, {"PREPLY_PROXY_URL": "http://env-proxy:8080"}):
            self.assertEqual(
                resolve_proxy_url("http://cli-proxy:9090"),
                "http://cli-proxy:9090",
            )

    def test_explicit_none_or_direct_disables_proxy(self):
        with mock.patch.dict(os.environ, {"PREPLY_PROXY_URL": "http://env-proxy:8080"}):
            self.assertIsNone(resolve_proxy_url("none"))
            self.assertIsNone(resolve_proxy_url("direct"))
            self.assertIsNone(resolve_proxy_url("off"))
            self.assertIsNone(resolve_proxy_url(""))

    def test_environment_variable_precedence(self):
        # 1. PREPLY_PROXY_URL over DATAIMPULSE_PROXY_URL
        with mock.patch.dict(
            os.environ,
            {
                "PREPLY_PROXY_URL": "http://preply-p:1111",
                "DATAIMPULSE_PROXY_URL": "http://dataimpulse-p:2222",
                "HTTPS_PROXY": "http://system-p:3333",
            },
            clear=True,
        ):
            self.assertEqual(resolve_proxy_url(), "http://preply-p:1111")

        # 2. DATAIMPULSE_PROXY_URL over HTTPS_PROXY
        with mock.patch.dict(
            os.environ,
            {
                "DATAIMPULSE_PROXY_URL": "http://dataimpulse-p:2222",
                "HTTPS_PROXY": "http://system-p:3333",
            },
            clear=True,
        ):
            self.assertEqual(resolve_proxy_url(), "http://dataimpulse-p:2222")

        # 3. HTTPS_PROXY when others unset
        with mock.patch.dict(
            os.environ,
            {"HTTPS_PROXY": "http://system-p:3333"},
            clear=True,
        ):
            self.assertEqual(resolve_proxy_url(), "http://system-p:3333")

    def test_mask_proxy_redacts_credentials(self):
        self.assertEqual(
            mask_proxy("http://user:secret123@gw.dataimpulse.com:823"),
            "http://user:***@gw.dataimpulse.com:823",
        )
        self.assertEqual(
            mask_proxy("http://gw.dataimpulse.com:823"),
            "http://gw.dataimpulse.com:823",
        )
        self.assertEqual(mask_proxy(None), "none")


class TransportChallengeDetectionTests(unittest.TestCase):
    def test_detects_just_a_moment_challenge(self):
        html = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
        self.assertTrue(_is_cloudflare_challenge(403, html))
        self.assertTrue(_is_cloudflare_challenge(429, html))
        self.assertFalse(_is_cloudflare_challenge(200, html))

    def test_detects_turnstile_challenge(self):
        html = "<!DOCTYPE html><html><body><div id='cf-turnstile'></div></body></html>"
        self.assertTrue(_is_cloudflare_challenge(403, html))

    def test_normal_json_or_error_not_treated_as_challenge(self):
        self.assertFalse(_is_cloudflare_challenge(404, "Not Found"))
        self.assertFalse(_is_cloudflare_challenge(500, '{"error": "internal"}'))


class TransportGraphqlParsingTests(unittest.TestCase):
    def test_parse_valid_graphql_payload(self):
        raw = '{"data": {"tutor": {"id": 123}}}'
        data = _parse_graphql_payload("TestOp", 200, raw, "direct")
        self.assertEqual(data["tutor"]["id"], 123)
        self.assertEqual(data["_egress"], "direct")

    def test_parse_graphql_errors_raises_transport_error(self):
        raw = '{"errors": [{"message": "Cannot query field"}]}'
        with self.assertRaises(PreplyTransportError) as caught:
            _parse_graphql_payload("TestOp", 200, raw, "direct")
        self.assertIn("Cannot query field", str(caught.exception))

    def test_non_json_raises_transport_error(self):
        with self.assertRaises(PreplyTransportError) as caught:
            _parse_graphql_payload("TestOp", 502, "Bad Gateway", "direct")
        self.assertIn("non-JSON response", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
