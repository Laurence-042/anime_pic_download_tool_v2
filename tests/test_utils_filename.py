import unittest

from utils.filename import clean_source_from_url, infer_url_from_filename


class FilenameTests(unittest.TestCase):
    def test_clean_source(self):
        self.assertEqual(
            clean_source_from_url("https://www.pixiv.net/artworks/123"),
            "pixiv_123",
        )
        self.assertEqual(
            clean_source_from_url("https://x.com/user/status/1234567890123456789"),
            "twitter_user_1234567890123456789",
        )
        self.assertEqual(
            clean_source_from_url("https://www.example.com/a/b"),
            "example.com_a_b",
        )
        self.assertEqual(clean_source_from_url(""), "unknown")

    def test_infer_url(self):
        self.assertEqual(
            infer_url_from_filename("pixiv_123_p0.png"),
            "https://www.pixiv.net/artworks/123",
        )
        self.assertEqual(
            infer_url_from_filename("twitter_abc_123456789012345_1.comfy.jpg"),
            "https://x.com/abc/status/123456789012345",
        )
        self.assertEqual(
            infer_url_from_filename("gelbooru_77_a_u.png"),
            "https://gelbooru.com/index.php?page=post&s=view&id=77",
        )


if __name__ == "__main__":
    unittest.main()
