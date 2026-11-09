from sqlalchemy import text

from app.database.database import engine


def migrate_location():

    with engine.begin() as connection:

        print("Creating locations table...")

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS locations (
                    id SERIAL PRIMARY KEY,

                    city VARCHAR(100) NOT NULL,
                    state VARCHAR(100),
                    country VARCHAR(100),

                    normalized_city VARCHAR(100) NOT NULL,
                    normalized_state VARCHAR(100),
                    normalized_country VARCHAR(100)
                );
                """
            )
        )

        print("Adding indexes to locations...")

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_locations_city
                ON locations(city);
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_locations_state
                ON locations(state);
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_locations_country
                ON locations(country);
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_locations_normalized_city
                ON locations(normalized_city);
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_locations_normalized_state
                ON locations(normalized_state);
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_locations_normalized_country
                ON locations(normalized_country);
                """
            )
        )

        print("Adding location_id to candidates...")

        connection.execute(
            text(
                """
                ALTER TABLE candidates
                ADD COLUMN IF NOT EXISTS location_id INTEGER;
                """
            )
        )

        print("Adding foreign key...")

        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'fk_candidates_location_id'
                    ) THEN

                        ALTER TABLE candidates
                        ADD CONSTRAINT fk_candidates_location_id
                        FOREIGN KEY (location_id)
                        REFERENCES locations(id);

                    END IF;
                END
                $$;
                """
            )
        )

        print("Adding candidates.location_id index...")

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_candidates_location_id
                ON candidates(location_id);
                """
            )
        )

    print("\nLocation migration completed successfully.")


if __name__ == "__main__":
    migrate_location()