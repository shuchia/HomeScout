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


# ── Recall-tune additions (co-living / by-the-room), precision-guarded ──

def test_coliving_high_confidence():
    for desc in ["Modern co-living community", "Premier coliving in the city"]:
        r = detect_pricing_model(desc, bedrooms=2, bathrooms=1, rent=1200, city="Boston")
        assert r["pricing_model"] == "per_person", desc


def test_rent_by_the_room():
    r = detect_pricing_model("Rent by the room in a renovated brownstone",
                             bedrooms=4, bathrooms=2, rent=1000, city="Boston")
    assert r["pricing_model"] == "per_person"


def test_roostup_operator():
    """Real RoostUp (Cambridge) listing that was tagged per_unit before the tune —
    beds != baths and no classic keyword, but the operator + model are by-the-room."""
    r = detect_pricing_model(
        description=("RoostUp is offering a beautifully renovated private bedroom in "
                     "Cambridge. Less than a 15 minute walk to Kendall Sq in a 4 "
                     "bedroom/2 bath apartment."),
        bedrooms=4, bathrooms=2, rent=1400, city="Cambridge",
    )
    assert r["pricing_model"] == "per_person"


def test_per_bedroom_lease():
    r = detect_pricing_model("Per-bedroom lease available for students",
                             bedrooms=3, bathrooms=1, rent=900, city="Philadelphia")
    assert r["pricing_model"] == "per_person"


# ── Precision guards: whole-unit luxury must NOT trip on the new mediums ──

def test_private_bedroom_alone_stays_per_unit():
    """"private bedroom" is a common luxury phrase — 0.3 medium alone must not flag."""
    r = detect_pricing_model(
        description="Each residence features a private bedroom with ensuite bath and walk-in closet.",
        bedrooms=3, bathrooms=1, rent=4500, city="Boston",
    )
    assert r["pricing_model"] == "per_unit"


def test_private_bedroom_in_bedsbaths_luxury_stays_per_unit():
    """Even in a beds==baths (3/3) luxury unit, 'private bedroom' (0.3) + beds==baths
    (0.25) = 0.55 stays below threshold — no false positive."""
    r = detect_pricing_model(
        description="Spacious 3 bedroom residence; each private bedroom is generously sized.",
        bedrooms=3, bathrooms=3, rent=6000, city="Cambridge",
    )
    assert r["pricing_model"] == "per_unit"


def test_luxury_conventional_stays_per_unit():
    """Real conventional 3/3 luxury description (260 Huntington-style) stays per_unit."""
    r = detect_pricing_model(
        description=("Perfectly positioned at the intersection of Fenway, Back Bay, and "
                     "the South End, Lyra places you at the center of Boston's cultural pulse."),
        bedrooms=3, bathrooms=3, rent=7000, city="Boston",
    )
    assert r["pricing_model"] == "per_unit"


# --- Room in a shared house -------------------------------------------------
#
# The detector's vocabulary was built for purpose-built student co-living and
# had no word for the commoner case: renting one room in a share. 5 Linden St,
# Boston scored 0.4 against a 0.6 threshold and was published as a whole 4-bed
# Allston house for $1,130. 90 listings across five markets were wrong the
# same way — and every such error runs in the too-good-to-be-true direction,
# so the heuristic ranks it straight to the top.

_LINDEN_DESC = (
    "Room for rent: PLEASE NOTE: This is a private room in a shared apartment. "
    "You will have your own bedroom and shared common areas (kitchen, bathroom, "
    "etc.) with other residents. Full bedroom in a 4 bedroom / 1 bathroom "
    "apartment! This Full room in Allston offers flexible lease lengths. "
    "Speak to a June representative for recommendations."
)
_LINDEN_URL = (
    "https://www.apartments.com/"
    "room-in-shared-4-bed-1-bath-home-in-allston-boston-ma/0yt4pd0/"
)


def test_linden_street_description_is_per_person():
    r = detect_pricing_model(
        description=_LINDEN_DESC, bedrooms=4, bathrooms=1, rent=1130, city="Boston"
    )
    assert r["pricing_model"] == "per_person"


def test_url_slug_alone_is_enough():
    """The slug is built from the listing title and is often more explicit than
    the prose. It costs nothing to read and was being ignored."""
    r = detect_pricing_model(
        description="", bedrooms=7, bathrooms=2.5, rent=1610, city="Cambridge",
        source_url="https://www.apartments.com/room-in-shared-7-bed-2-5-bath-home-in-harvard-square-cambridge-ma/x/",
    )
    assert r["pricing_model"] == "per_person"


def test_source_url_is_optional():
    """Three call sites exist; the parameter must stay backward compatible."""
    r = detect_pricing_model(
        description=_LINDEN_DESC, bedrooms=4, bathrooms=1, rent=1130, city="Boston"
    )
    assert "pricing_model" in r


def test_beds_far_exceeding_baths_does_not_flip_alone():
    """Geometry is a safety net, not a signal. An ordinary family home with
    more beds than baths and no by-the-room language stays per_unit."""
    r = detect_pricing_model(
        description="Lovely family home with a large yard and finished basement.",
        bedrooms=4, bathrooms=2, rent=3800, city="Boston",
    )
    assert r["pricing_model"] == "per_unit"
    assert r["uncertain"] is False


def test_uncertain_marks_evidence_that_fell_short():
    """Real evidence below the threshold must not read as a confident
    per_unit. Reporting 'confidence 0.6' in the wrong answer is how 5 Linden
    shipped."""
    r = detect_pricing_model(
        description="Each residence features a private bedroom with ensuite bath.",
        bedrooms=3, bathrooms=1, rent=4500, city="Boston",
    )
    assert r["pricing_model"] == "per_unit"
    assert r["uncertain"] is True


def test_clear_per_unit_is_not_marked_uncertain():
    r = detect_pricing_model(
        description="Modern finishes throughout, in-unit laundry.",
        bedrooms=2, bathrooms=2, rent=3200, city="Boston",
    )
    assert r["uncertain"] is False
