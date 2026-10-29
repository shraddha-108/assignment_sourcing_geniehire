from app.database.base import Base
from app.database.database import engine

# Import every model so SQLAlchemy registers all tables.
from app.database import models


def init_db() -> None:
    Base.metadata.create_all(
        bind=engine,
    )


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully.")