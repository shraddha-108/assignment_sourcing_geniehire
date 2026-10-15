from database import SessionLocal
from models import Candidate, CandidateSkill, Experience

db = SessionLocal()

try:
    print("Checking database...")

    print("Candidates:", db.query(Candidate).count())
    print("Skills:", db.query(CandidateSkill).count())
    print("Experiences:", db.query(Experience).count())

finally:
    db.close()