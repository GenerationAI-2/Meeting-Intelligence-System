"""Regression tests for token hashing in manage_tokens.py.

Verifies that hash_token() produces a single SHA256 hash identical
to what main.py:validate_mcp_token() computes. Catches regressions
if someone changes hash_token to double-hash or a different algorithm.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from manage_tokens import hash_token


class TestTokenHash:
    """Regression tests for hash_token alignment with main.py."""

    def test_single_sha256_matches_direct_hashlib(self):
        """hash_token must produce identical output to hashlib.sha256().hexdigest()."""
        token = "test-token-abc123"
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert hash_token(token) == expected

    def test_no_double_hash(self):
        """hash_token must NOT double-hash. SHA256(SHA256(x)) != SHA256(x)."""
        token = "my-secret-token"
        single = hashlib.sha256(token.encode()).hexdigest()
        double = hashlib.sha256(single.encode()).hexdigest()
        result = hash_token(token)
        assert result == single
        assert result != double

    def test_different_tokens_different_hashes(self):
        """Distinct tokens must produce distinct hashes."""
        assert hash_token("token-a") != hash_token("token-b")

    def test_deterministic(self):
        """Same input must always produce same output."""
        token = "deterministic-test"
        assert hash_token(token) == hash_token(token)

    def test_output_is_hex_string(self):
        """Output should be a 64-character hex string (SHA256)."""
        result = hash_token("any-token")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_string(self):
        """Edge case: empty string should still hash correctly."""
        expected = hashlib.sha256(b"").hexdigest()
        assert hash_token("") == expected

    def test_unicode_token(self):
        """Tokens with unicode characters should hash correctly."""
        token = "token-\u00e9\u00e8\u00ea"
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert hash_token(token) == expected

    def test_matches_main_py_pattern(self):
        """Explicit test of the exact pattern from main.py:validate_mcp_token().

        main.py line 54: hashlib.sha256(token.encode()).hexdigest()
        """
        token = "real-looking-token_abc123XYZ"
        main_py_hash = hashlib.sha256(token.encode()).hexdigest()
        assert hash_token(token) == main_py_hash
