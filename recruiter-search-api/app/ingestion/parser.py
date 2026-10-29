from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.ingestion.schemas.resume import ResumeData


load_dotenv()


MODEL_NAME = "gpt-6-luna"


SYSTEM_PROMPT = """
You are a professional resume information extraction system.

Your job is to extract structured information from the supplied resume.

The resume itself is the source of truth.

STRICT RULES:

1. Extract only information explicitly supported by the resume.

2. Never invent, guess, infer, or fabricate information.

3. If information is unavailable, return null or an empty list.

4. Preserve relationships between candidate, employment,
   technologies, projects, and education.

5. Do not reduce the resume to a flat list of skills.

6. Skills mentioned in a general skills section must not automatically
   be attached to an employment experience.

7. Attach skills to an experience only when the resume provides
   evidence that the skill was used in that experience.

8. Attach skills to a project only when the project text supports
   that technology or skill.

9. Preserve the original wording of evidence as closely as possible.

10. Evidence must not be a summary or paraphrase.

11. Do not generate new sentences for evidence.

12. Do not combine unrelated resume sections.

13. Projects must remain separate from employment experiences.

14. If multiple projects exist, return one ProjectData object
    for each identifiable project.

15. Do not merge multiple projects into one project.

16. Do not split one project into multiple projects.

17. For employment dates:
    - Extract dates directly from the employment entry.
    - Never derive employment dates from project dates.
    - Never derive employment dates from education dates.
    - If the resume says "Present" or "Current", return null
      for end_date.
    - If only month and year are available, use the first day
      of that month.

18. Do NOT calculate experience duration.

19. Do NOT calculate total experience.

20. Do NOT determine whether a candidate qualifies for any
    recruiter requirement.

21. Do NOT rank the candidate.

22. Do NOT infer years of experience from a skill list.

23. Preserve candidate URLs only when explicitly present.
24. Extract the candidate's explicitly stated current city/location into
    candidate.location. Return null when the resume does not state it.

24. Extract the candidate's actual name.
    Never use an email, URL, company name, project name,
    job title, skill, or section heading as the person's name.

25. For every employment experience, evidence must contain the
    complete original resume text belonging to that employment entry,
    including the role/company heading and all responsibilities,
    achievements, technologies, dates, and other text that belongs
    to that experience.

26. For every project, evidence must contain the complete original
    resume text belonging to that project.

27. Project evidence MUST NOT contain only the project title when
    the resume contains additional project-specific text.

28. For every project:
    - title = project name/title only.
    - description = project description explicitly present in the resume.
    - skills = technologies/skills explicitly associated with that project.
    - evidence = complete original resume text belonging to that project.

29. If a project has a title and additional description/details in
    the resume, include ALL of that project-specific text in evidence.

30. Do not replace project evidence with a summary, paraphrase,
    or generated description.

31. Do not use the project title alone as evidence unless the resume
    genuinely contains no other text belonging to that project.

32. Do not copy text from another project, employment experience,
    education, or unrelated section into project evidence.

33. If the same project contains multiple lines, bullets, technologies,
    responsibilities, dates, or achievements, preserve them together
    as one project's evidence.

34. Extract explicitly mentioned skills from the entire resume,
    not only from a section called "Skills".

35. If no projects exist, return an empty projects list.

36. If no education exists, return an empty education list.

37. If no employment exists, return an empty experiences list.
"""


def _create_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL_NAME,
    )


def parse_resume(text: str) -> ResumeData:
    if not text or not text.strip():
        raise ValueError(
            "Resume text cannot be empty."
        )

    llm = _create_llm()

    structured_llm = llm.with_structured_output(
        ResumeData,
        method="json_schema",
    )

    prompt = f"""
Extract the resume into the required ResumeData schema.

Remember:

- Do not invent information.
- Do not calculate experience.
- Preserve employment/project relationships.
- Preserve evidence wording exactly as much as possible.
- Project evidence must contain the complete original text
  belonging to that project.
- Do not use only a project title as evidence when additional
  project information exists.
- Return null when information is unavailable.

RESUME:

{text}
"""

    result = structured_llm.invoke(
        [
            (
                "system",
                SYSTEM_PROMPT,
            ),
            (
                "human",
                prompt,
            ),
        ]
    )

    if result is None:
        raise ValueError(
            "LLM returned no structured resume data."
        )

    return result
