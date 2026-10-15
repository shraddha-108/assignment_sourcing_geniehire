from database import Base, engine
from models import Candidate, CandidateSkill, Experience

print("Resetting database schema...")

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

print("Database schema recreated successfully.")