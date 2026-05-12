import unittest

from main import parse_input_lines


class ParseInputLinesTests(unittest.TestCase):
    def test_parse_with_rvk_and_all(self):
        lines = [
            "# comment",
            "https://www.pixiv.net/artworks/111",
            "https://www.pixiv.net/artworks/222 all",
            "rvk",
            "https://www.pixiv.net/artworks/333 0 16",
            "https://www.pixiv.net/artworks/444 # comment only",
            "ignored text",
        ]
        self.assertEqual(
            parse_input_lines(lines),
            [
                ("https://www.pixiv.net/artworks/111", None),
                ("https://www.pixiv.net/artworks/333", [0, 16]),
                ("https://www.pixiv.net/artworks/444", None),
            ],
        )

    def test_rvk_when_empty_is_ignored(self):
        self.assertEqual(parse_input_lines(["rvk", "RVK"]), [])


if __name__ == "__main__":
    unittest.main()
