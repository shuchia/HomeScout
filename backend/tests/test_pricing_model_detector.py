import pytest
from app.services.pricing_model_detector import detect_pricing_model


def test_individual_lease_high_confidence():
    result = detect_pricing_model(
        description="Brand new student housing with individual lease options",
        bedrooms=4, bathrooms=4, rent=1030, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"
    assert result["confidence"] >= 0.7


def test_per_person_in_description():
    result = detect_pricing_model(
        description="Rent is $1,030 per person per month",
        bedrooms=2, bathrooms=2, rent=1030, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"
    assert result["confidence"] >= 0.8


def test_by_the_bed():
    result = detect_pricing_model(
        description="Lease by the bed in our modern community",
        bedrooms=3, bathrooms=3, rent=800, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"


def test_one_on_centre_description():
    """Real description from One on Centre Pittsburgh."""
    result = detect_pricing_model(
        description="Modern amenities you would expect from a brand new off-campus student housing community. Prices shown are base rent. Additional fees apply.",
        bedrooms=2, bathrooms=2, rent=1500, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"


def test_beds_equal_baths_with_student():
    result = detect_pricing_model(
        description="Located near the university, student friendly community",
        bedrooms=4, bathrooms=4, rent=900, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"


def test_normal_apartment():
    result = detect_pricing_model(
        description="Beautiful 2BR apartment in downtown Philadelphia",
        bedrooms=2, bathrooms=1, rent=1800, city="Philadelphia",
    )
    assert result["pricing_model"] == "per_unit"
    assert result["confidence"] >= 0.9


def test_studio_never_per_person():
    result = detect_pricing_model(
        description="Student studio near campus with individual lease",
        bedrooms=0, bathrooms=1, rent=1200, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_unit"


def test_beds_not_equal_baths_no_signals():
    result = detect_pricing_model(
        description="Spacious 4 bedroom apartment near park",
        bedrooms=4, bathrooms=2, rent=600, city="New York",
    )
    assert result["pricing_model"] == "per_unit"


def test_student_alone_not_sufficient():
    result = detect_pricing_model(
        description="Near student campus, great restaurants",
        bedrooms=2, bathrooms=1, rent=1500, city="Boston",
    )
    assert result["pricing_model"] == "per_unit"


def test_per_room_in_description():
    result = detect_pricing_model(
        description="Furnished rooms available, $900 per room",
        bedrooms=3, bathrooms=2, rent=900, city="Philadelphia",
    )
    assert result["pricing_model"] == "per_person"
