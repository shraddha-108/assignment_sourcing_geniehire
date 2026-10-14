from datetime import date
from database import Base, engine, SessionLocal
from models import Candidate, CandidateSkill, Experience

Base.metadata.create_all(engine)   # creates the tables if they don't exist

db = SessionLocal()

candidate = Candidate(name="Test Person", email="test@example.com")

candidate.experiences.append(
    Experience(
        company="Acme Corp",
        title="Backend Developer",
        start_date=date(2022, 1, 1),
        end_date=None,   # still working there
    )
)

candidate.skills.append(
    CandidateSkill(skill="python", last_used_date=date.today(), total_months=48)
)

db.add(candidate)   # stage it
db.commit()         # save it to PostgreSQL
print("Saved candidate with id", candidate.id)
db.close()