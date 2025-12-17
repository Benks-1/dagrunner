import unittest
from dagrunner import resolve_placeholders


class TestPlaceholdersMissing(unittest.TestCase):
    def test_exact_placeholder_missing_raises(self):
        outputs = {}
        with self.assertRaises(KeyError):
            resolve_placeholders("${outputs.nope.return_value}", outputs)

    def test_embedded_placeholder_missing_keeps_literal(self):
        outputs = {}
        s = "Value: ${outputs.nope.return_value}"
        out = resolve_placeholders(s, outputs)
        # should keep the original placeholder text because _sub returns the literal on KeyError
        self.assertIn("${outputs.nope.return_value}", out)
