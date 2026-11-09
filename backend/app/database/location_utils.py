from app.database.models.location import Location


def normalize_location(value: str | None) -> str:
    return " ".join((value or "").casefold().strip().split())


def format_candidate_location(location: Location | None) -> str | None:
    if location is None:
        return None
    return ", ".join(
        part for part in (location.city, location.state, location.country) if part
    ) or None



def location_matches(requested: str | dict | None, location: Location | None) -> bool:
    """Match legacy text or structured Geoapify city/state/country values."""
    if location is None or not requested:
        return False
    city = normalize_location(location.normalized_city or location.city)
    state = normalize_location(location.normalized_state or location.state)
    country = normalize_location(location.normalized_country or location.country)

    if isinstance(requested, dict):
        requested_city = normalize_location(requested.get("city"))
        requested_state = normalize_location(requested.get("state"))
        requested_country = normalize_location(requested.get("country"))
        if not any((requested_city, requested_state, requested_country)):
            return False
        return (
            (not requested_city or city == requested_city)
            and (not requested_state or state == requested_state)
            and (not requested_country or country == requested_country)
        )

    requested_value = normalize_location(requested)
    if not requested_value:
        return False
    if requested_value in {"india", "bharat"}:
        return not country or country in {"india", "bharat"}
    if requested_value in {"maharashtra", "mh"}:
        return state in {"maharashtra", "mh"}
    return requested_value in {city, state, country}
