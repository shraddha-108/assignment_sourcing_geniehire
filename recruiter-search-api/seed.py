from datetime import date, timedelta
import random

from faker import Faker

from database import Base, engine, SessionLocal
from models import Candidate, CandidateSkill, Experience

Base.metadata.create_all(engine)

fake = Faker("en_IN")
today = date.today()

NUM_CANDIDATES = 1000

SKILLS = [
    "python", "sql", "java", "javascript", "typescript",
    "react", "nodejs", "fastapi", "django",
    "postgresql", "mongodb", "aws", "docker",
    "kubernetes", "pytorch", "tensorflow", "machine learning",
    "nlp", "llm", "langchain"
]

COMPANIES = [
    "TCS", "Infosys", "Accenture", "Wipro", "Cognizant",
    "Capgemini", "Tech Mahindra", "Persistent Systems",
    "Zoho", "Freshworks", "Microsoft", "Amazon",
    "Google", "Deloitte", "GenieHire"
]

TITLES = [
    "Software Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Full Stack Developer",
    "Python Developer",
    "AI Engineer",
    "ML Engineer",
    "Data Scientist",
    "Senior Software Engineer",
    "Software Developer"
]


def months_ago(months: int) -> date:
    return today - timedelta(days=30 * months)


def random_experience():
    end_months_ago = random.randint(0, 24)
    duration_months = random.randint(6, 60)

    end_date = months_ago(end_months_ago)
    start_date = end_date - timedelta(days=30 * duration_months)

    return start_date, end_date


db = SessionLocal()

try:
    print("Clearing old data...")

    db.query(CandidateSkill).delete()
    db.query(Experience).delete()
    db.query(Candidate).delete()
    db.commit()

    print("Generating candidates...")

    candidates = []

    for _ in range(NUM_CANDIDATES):
        candidate = Candidate(
            name=fake.name(),
            email=fake.unique.email()
        )

        skill_count = random.randint(3, 8)
        candidate_skills = random.sample(SKILLS, skill_count)

        for skill in candidate_skills:
            last_used_months_ago = random.randint(0, 60)
            total_months = random.randint(6, 96)

            candidate.skills.append(
                CandidateSkill(
                    skill=skill,
                    last_used_date=months_ago(last_used_months_ago),
                    total_months=total_months
                )
            )

        experience_count = random.randint(1, 4)

        for _ in range(experience_count):
            start_date, end_date = random_experience()

            candidate.experiences.append(
                Experience(
                    company=random.choice(COMPANIES),
                    title=random.choice(TITLES),
                    start_date=start_date,
                    end_date=end_date
                )
            )

        candidates.append(candidate)

    db.add_all(candidates)
    db.commit()

    total_skills = db.query(CandidateSkill).count()
    total_experiences = db.query(Experience).count()

    print(f"Seeded {NUM_CANDIDATES} candidates")
    print(f"Seeded {total_skills} candidate skills")
    print(f"Seeded {total_experiences} experiences")

finally:
    db.close()