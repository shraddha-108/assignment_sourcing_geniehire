from app.database.models.location import Location


def normalize_location(value: str | None) -> str:
    return " ".join((value or "").casefold().strip().split())


def format_candidate_location(location: Location | None) -> str | None:
    if location is None:
        return None
    return ", ".join(
        part for part in (location.city, location.state, location.country) if part
    ) or None


_MAHARASHTRA_CITIES = {
    "aurangabad", "chhatrapati sambhajinagar", "jalgaon", "kolhapur",
    "mumbai", "nagpur", "nanded", "nashik", "navi mumbai", "pune",
    "sangli", "satara", "solapur", "thane", "vasai", "virar",
}


def location_matches(requested: str | None, location: Location | None) -> bool:
    requested_value = normalize_location(requested)
    if not requested_value or location is None:
        return False

    city = normalize_location(location.normalized_city or location.city)
    state = normalize_location(location.normalized_state or location.state)
    country = normalize_location(location.normalized_country or location.country)

    if requested_value in {"india", "bharat"}:
        # A missing country is treated as India for this India-focused resume corpus.
        return not country or country in {"india", "bharat"}

    if requested_value in {"maharashtra", "mh"}:
        return state in {"maharashtra", "mh"} or city in _MAHARASHTRA_CITIES

    return requested_value in {city, state, country}
