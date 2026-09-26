from app.services.tours import _amendment_change_type


def test_combined_discount_amendment_history_label_fits_database_column():
    label = _amendment_change_type(["validity_extended", "percentage_changed"])

    assert label == "validity_and_value_changed"
    assert len(label) <= 30


def test_single_discount_amendment_keeps_specific_history_label():
    assert _amendment_change_type(["validity_extended"]) == "validity_extended"
    assert _amendment_change_type(["percentage_changed"]) == "percentage_changed"
