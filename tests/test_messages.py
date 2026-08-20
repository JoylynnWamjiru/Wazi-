"""Language-aware refusal and fallback messages."""

from src.shared.messages import no_answer, system_error


def test_no_answer_english_for_english_query():
    text = no_answer("Why did the Njoro hospital stall?")
    assert text.startswith("I'm sorry, I don't have the answer")


def test_no_answer_swahili_for_swahili_query():
    text = no_answer("mradi wa njoro imeisha")
    assert text.startswith("Samahani, sina jibu")


def test_no_answer_swahili_for_terse_swahili_query():
    # One Swahili marker is enough for a query (unlike the 2-hit reply detector).
    assert no_answer("pesa ngapi").startswith("Samahani")


def test_system_error_english_for_english_query():
    assert system_error("what is the county budget").startswith("Sorry, I'm having")


def test_system_error_swahili_for_swahili_query():
    assert system_error("pesa ngapi").startswith("Samahani, mtandao wangu")


def test_system_error_english_for_english_na_abbreviation():
    # "NA" -> "na" must not flip a short English query to Swahili.
    assert system_error("The value is NA for this line item").startswith("Sorry")
