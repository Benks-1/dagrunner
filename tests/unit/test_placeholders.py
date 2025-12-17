import unittest
from dagrunner import resolve_placeholders

class TestPlaceholders(unittest.TestCase):
    def test_string_substitution_and_exact_match(self):
        outputs = {
            "producer": {"returncode": 0, "return_value": {"x": 42, "msg": "ok"}}
        }
        # embedded
        s = "Value is ${outputs.producer.return_value.x}!"
        out = resolve_placeholders(s, outputs)
        self.assertIn("42", out)
        # exact match returns raw object
        s2 = "${outputs.producer.return_value}"
        out2 = resolve_placeholders(s2, outputs)
        self.assertIsInstance(out2, dict)
        self.assertEqual(out2.get("x"), 42)

if __name__ == "__main__":
    unittest.main()
