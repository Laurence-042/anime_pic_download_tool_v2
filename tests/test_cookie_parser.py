import tempfile
import unittest
from pathlib import Path

from cookie_parser import parse_cookie_file


class CookieParserTests(unittest.TestCase):
    def test_parse_netscape_cookie(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "cookies.txt"
            p.write_text(
                "# Netscape HTTP Cookie File\n"
                ".twitter.com\tTRUE\t/\tTRUE\t0\tauth_token\txxxxx\n",
                encoding="utf-8",
            )
            cookies = parse_cookie_file(str(p))
            self.assertEqual(len(cookies), 1)
            c = cookies[0]
            self.assertEqual(c["name"], "auth_token")
            self.assertEqual(c["value"], "xxxxx")
            self.assertEqual(c["domain"], ".twitter.com")
            self.assertEqual(c["path"], "/")
            self.assertEqual(c["sameSite"], "Lax")


if __name__ == "__main__":
    unittest.main()
