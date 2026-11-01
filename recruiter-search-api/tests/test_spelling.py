import unittest

from app.search.spelling import suggest_query_correction


class SpellingTests(unittest.TestCase):
    def test_suggests_correction_for_adjacent_transposition(self):
        self.assertEqual(
            suggest_query_correction(
                "candidates who has worked on machine learning proejcts"
            ),
            "candidates who has worked on machine learning projects",
        )

    def test_does_not_suggest_correction_for_correct_query(self):
        self.assertIsNone(suggest_query_correction("machine learning projects"))


if __name__ == "__main__":
    unittest.main()
