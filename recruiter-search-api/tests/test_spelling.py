import unittest

from app.search.spelling import build_speller, suggest_query_correction


class SpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_speller()

    def test_suggests_correction_for_adjacent_transposition(self):
        self.assertEqual(
            suggest_query_correction(
                "candidates who has worked on machine learning proejcts"
            ),
            "candidates who has worked on machine learning projects",
        )

    def test_does_not_suggest_correction_for_correct_query(self):
        self.assertIsNone(suggest_query_correction("machine learning projects"))

    def test_suggests_corrections_from_the_dictionary(self):
        self.assertEqual(
            suggest_query_correction("find a software pyhton"),
            "find a software python",
        )

    def test_preserves_known_technical_terms_and_names(self):
        self.assertIsNone(suggest_query_correction("Find Python developers in D365"))

    def test_does_not_change_unknown_words_without_a_clear_match(self):
        self.assertIsNone(suggest_query_correction("Find candidates in Xyzzqv"))

    def test_preserves_unknown_acronyms(self):
        self.assertIsNone(suggest_query_correction("Find candidates with XYZQ"))

    def test_uses_dictionary_ranking_for_ambiguous_typo(self):
        self.assertEqual(
            suggest_query_correction("Find software enginer"),
            "Find software engineer",
        )


if __name__ == "__main__":
    unittest.main()
