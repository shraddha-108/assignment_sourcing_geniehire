from pathlib import Path
from pprint import pprint

from ingestion.postgresql.extractor import extract_text
from ingestion.postgresql.llm_parser import parse_resume_with_llm


path = Path("data/Abhishek_Premkumar_Sawale_FullStack_Developer_Python_and_React.pdf")

text = extract_text(path)

print("\n--- RAW TEXT ---")
print(text)

data = parse_resume_with_llm(text)

print("\n--- PROJECTS FROM LLM ---")
pprint(data["evidence"]["projects"])