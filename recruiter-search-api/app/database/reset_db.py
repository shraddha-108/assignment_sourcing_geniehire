from app.database.database import engine
from app.database.base import Base

# Import ALL models so SQLAlchemy knows about every table.
from app.database.models import (
    Candidate,
    Company,
    Role,
    Experience,
    Skill,
    CandidateSkill,
    ExperienceSkill,
    TechnologyDomain,
    TechnologyDomainMember,
    Project,
    ProjectSkill,
    Education,
    Resume,
    ResumeSection,
    CandidateEvidence,
    IngestionRun,
    Location,
)


def reset_database():
    print("Dropping existing tables...")
    Base.metadata.drop_all(bind=engine)

    print("Creating tables from current SQLAlchemy models...")
    Base.metadata.create_all(bind=engine)

    print("Database reset completed successfully.")


if __name__ == "__main__":
    reset_database()