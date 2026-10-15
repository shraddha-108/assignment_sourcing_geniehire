from ingestion.postgresql.parser import parse_resume
from ingestion.postgresql.experience_extractor import (
    find_experience_section,
    extract_experiences,
)


sample_text = """
Mrs. GARIMA ARJUN GOHAD
Mobile No.: 9075393202
E-Mail:- garimagcharpe3@gmail.com

Summary:

Persuasive & result oriented professional with around 4.5 years of experience in the IT and Non-IT recruiting field.

Employment History:-

Organization Role Duration
MPower Plus Talent Acquisition Executive June 2021 to April 2023
Andicon Services Pvt. Ltd. Talent Acquisition Executive Feb 2020 to May 2021
Accural Solutions HR Recruitment Consultant Sept 2018 to Dec 2019.

Computer Skills:

Operating Systems: Windows 10/8/7/XP/2000
Software’s: Microsoft Office 2010/2007

Job Responsibilities:-

MPower Plus
Talent Acquisition Executive
June 2021 to April 2023

Roles/Responsibilities:
Experience in handling the complete Recruitment Life Cycle.

Andicon Services Pvt. Ltd
Talent Acquisition Executive
Feb 2020 to May 2021

Roles/Responsibilities:
Worked on major part of IT, Non IT for entire Pan India Location.

Accural Solutions:
HR Recruitment Consultant
Sept 2018 to Dec 2019.

Roles/Responsibilities:
Employee Data Management in Microsoft office.

Educational Qualifications:-

Name Garima Arjun Gohad
"""


def test_experience_extractor():
    section = find_experience_section(sample_text)

    print("\n===== EXPERIENCE SECTION =====")
    print(section)

    experiences = extract_experiences(sample_text)

    print("\n===== EXPERIENCES =====")
    for experience in experiences:
        print(experience)

    assert section
    assert experiences
    assert len(experiences) >= 3


def test_parse_resume():
    result = parse_resume(
        text=sample_text,
        filename="Naukri_Garima_Arjun_Gohad_resume.pdf",
    )

    print("\n===== PARSED RESUME =====")
    print("NAME:", result["name"])
    print("EMAIL:", result["email"])
    print("PHONE:", result["phone"])
    print("SKILLS:", result["skills"])
    print("EXPERIENCES:", result["experiences"])

    assert result["name"]
    assert result["email"]
    assert result["phone"]
    assert result["experiences"]