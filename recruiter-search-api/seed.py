from datetime import date, timedelta
from database import Base, engine, SessionLocal
from models import Candidate, CandidateSkill, Experience

Base.metadata.create_all(engine)  # creates the tables if they don't exist

today = date.today()


def months_ago(n: int) -> date:
    return today - timedelta(days=30 * n)


# (name, email, [(skill, months since last used, total months)])
SAMPLE = [
    ("Aarav Mehta",   "aarav@example.com",   [("python", 0, 60), ("sql", 0, 48)]),
    ("Diya Sharma",   "diya@example.com",    [("python", 2, 36), ("react", 1, 24)]),
    ("Rohan Iyer",    "rohan@example.com",   [("python", 10, 72), ("django", 10, 40)]),
    ("Sneha Patil",   "sneha@example.com",   [("python", 30, 24), ("java", 6, 50)]),
    ("Kabir Singh",   "kabir@example.com",   [("java", 0, 84), ("sql", 3, 60)]),
    ("Meera Nair",    "meera@example.com",   [("react", 0, 40), ("typescript", 0, 36)]),
    ("Arjun Rao",     "arjun@example.com",   [("python", 5, 18), ("fastapi", 5, 12)]),
    ("Isha Kulkarni", "isha@example.com",    [("python", 48, 30), ("sql", 12, 20)]),
]

db = SessionLocal()

# Clear old rows so re-running the seed doesn't create duplicates
db.query(CandidateSkill).delete()
db.query(Experience).delete()
db.query(Candidate).delete()
db.commit()

for name, email, skills in SAMPLE:
    c = Candidate(name=name, email=email)
    c.experiences.append(
        Experience(company="Sample Corp", title="Software Engineer",
                   start_date=date(2021, 1, 1), end_date=None)
    )
    for skill, last_used_months_ago, total in skills:
        c.skills.append(
            CandidateSkill(skill=skill,
                           last_used_date=months_ago(last_used_months_ago),
                           total_months=total)
        )
    db.add(c)

db.commit()
print(f"Seeded {len(SAMPLE)} candidates")
db.close()