from database import SessionLocal
from models import Candidate, CandidateSkill, Experience

db = SessionLocal()

try:
    print("Clearing candidate data...")

    db.query(CandidateSkill).delete()
    db.query(Experience).delete()
    db.query(Candidate).delete()

    db.commit()

    print("Candidate data cleared successfully.")

finally:
    db.close()