from database import SessionLocal

from intelligence.service import (
    execute_structured_search,
)


def test_structured_search():

    db = SessionLocal()

    try:

        requirements = {
            "skills": ["python"],
            "recency_months": 12,
        }

        results = execute_structured_search(
            db=db,
            requirements=requirements,
            requested_count=10,
        )

        for result in results:
            print(
                result["candidate"].name,
                result["skill"],
                result["last_used_date"],
                result["total_months"],
                result["score"],
            )

        assert isinstance(results, list)

    finally:
        db.close()