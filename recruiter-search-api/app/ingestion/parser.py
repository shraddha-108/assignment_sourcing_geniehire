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

24. Extract the candidate's explicitly stated current city/location
    into candidate.location.

    - Use only location information explicitly stated for the candidate.
    - Do not infer location from a phone number, email address,
      company location, college location, project location,
      or any other indirect information.
    - If only a city is explicitly stated, extract the city.
    - If city/state/country are explicitly stated, preserve that
      location information.
    - If the candidate's location is not explicitly stated,
      return null.

25. Extract the candidate's actual name.

    Never use an email, URL, company name, project name, job title,
    skill, or section heading as the person's name.

26. For every employment experience, evidence must contain the
    complete original resume text belonging to that employment entry,
    including the role/company heading and all responsibilities,
    achievements, technologies, dates, and other text that belongs
    to that experience.

27. For every project, evidence must contain the complete original
    resume text belonging to that project.

28. Project evidence MUST NOT contain only the project title when
    the resume contains additional project-specific text.

29. For every project:
    - title = project name/title only.
    - description = project description explicitly present in the resume.
    - skills = valid technologies/skills explicitly associated with
      that project.
    - evidence = complete original resume text belonging to that project.

30. If a project has a title and additional description/details in
    the resume, include ALL of that project-specific text in evidence.

31. Do not replace project evidence with a summary, paraphrase,
    or generated description.

32. Do not use the project title alone as evidence unless the resume
    genuinely contains no other text belonging to that project.

33. Do not copy text from another project, employment experience,
    education, or unrelated section into project evidence.

34. If the same project contains multiple lines, bullets, technologies,
    responsibilities, dates, or achievements, preserve them together
    as one project's evidence.

35. The top-level `skills` list is only for skills explicitly listed
    in a dedicated candidate skills section (for example, "Skills",
    "Technical Skills", or "Core Competencies").

    Do not collect words from employment descriptions, project
    descriptions, education, summaries, or other resume text into
    this candidate-level list.

36. Keep technologies and skills mentioned in a job or project attached
    only to that experience or project when the surrounding text
    supports their use there.

    Do not copy those into the top-level `skills` list unless they
    are also explicitly listed in the dedicated skills section.


SKILL EXTRACTION RULES
======================

37. A "skill" must represent a real technical skill, technology,
    tool, framework, programming language, database, platform,
    methodology, professional competency, or clearly established
    domain expertise.

38. Do NOT treat every noun appearing in a project or experience
    description as a skill.

39. Do NOT extract ordinary business entities, objects, people,
    outputs, or things being worked on as skills.

40. The following are examples of things that should NOT automatically
    be extracted as skills:

    - customers
    - vendors
    - employees
    - users
    - clients
    - products
    - invoices
    - reports
    - documents
    - records
    - transactions
    - orders
    - accounts
    - business requirements
    - company names
    - project names
    - departments
    - job titles

41. A noun should only be extracted as a skill when the resume
    explicitly presents it as a professional competency, technical
    capability, or specialized domain expertise.

42. Examples:

    "Developed REST APIs using Python and FastAPI"

    Valid skills:
    - Python
    - FastAPI
    - REST API

    Do NOT extract:
    - APIs
    - applications
    - users
    - data


43. Example:

    "Master Data Creation for Customers, Vendors, Financial Dimensions"

    Valid skill:
    - Master Data Creation

    Do NOT extract:
    - customers
    - vendors

    "Financial Dimensions" should NOT automatically be treated as
    a skill merely because it appears in this sentence. Only extract
    it when the resume clearly establishes it as a specialized
    professional competency or domain expertise.

44. Example:

    "Built a Django application using PostgreSQL, Redis and Docker"

    Valid skills:
    - Django
    - PostgreSQL
    - Redis
    - Docker

    Do NOT extract:
    - application
    - users
    - database records

45. Example:

    "Performed testing and debugging of the application"

    Valid skill:
    - Testing
    - Debugging

    Do NOT extract:
    - application

46. Example:

    "Prepared functional design documents based on business
    requirements"

    Possible valid skill:
    - Functional Design

    Do NOT extract:
    - documents
    - business requirements

47. Prefer the actual technology or competency rather than the
    surrounding noun describing what was handled.

48. Do not create a skill by combining unrelated nouns.

49. Do not convert every project description phrase into a skill.

50. Do not extract generic words such as:
    - work
    - project
    - team
    - company
    - client
    - process
    - system
    - application
    - solution
    - data
    - information

    unless the resume clearly uses the term as part of a recognized
    professional skill or technology.

51. Preserve the skill wording from the resume when it clearly
    represents a skill.

52. Do not invent a more specific technology or competency than
    what the resume explicitly states.

53. For experience and project skills, include only skills that are
    explicitly supported by the surrounding experience/project text.

54. When uncertain whether a word is a skill or merely a business
    object/entity, prefer NOT extracting it as a skill.

55. The goal is a high-precision skill list, not a high-volume list.
    It is better to omit a questionable item than to store an
    ordinary business noun as a skill.


PROJECT RULES
=============

56. For every project, extract only genuine skills associated with
    that project.

57. Do not turn project description nouns into skills.

58. For example, if the project says:

    "Master Data Creation for Customers, Vendors, Financial Dimensions."

    the project skills should contain:

    ["Master Data Creation"]

    rather than:

    ["customers", "vendors", "financial dimensions", "master data creation"].


EXPERIENCE RULES
================

59. For every employment experience, extract only genuine skills
    demonstrated or explicitly mentioned in that experience.

60. Do not extract ordinary business objects from responsibilities
    as skills.

61. Preserve the distinction between:
    - technology
    - tool
    - methodology
    - professional competency
    - domain expertise
    - business object/entity


GENERAL RESUME RULES
====================

62. If no projects exist, return an empty projects list.

63. If no education exists, return an empty education list.

64. If no employment exists, return an empty experiences list.

65. If no valid skills are explicitly supported, return an empty
    skills list rather than guessing.
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
- Populate the top-level skills list only from a dedicated skills section.
- Do not promote words from projects, employment, education, or summaries
  into the top-level skills list.
- Preserve evidence wording exactly as much as possible.
- Project evidence must contain the complete original text
  belonging to that project.
- Do not use only a project title as evidence when additional
  project information exists.
- Extract candidate.location only when the candidate's location is
  explicitly stated in the resume.
- Do not infer location from phone numbers, email addresses,
  company locations, college locations, or other indirect information.
- Return null when information is unavailable.

IMPORTANT SKILL RULE:

For project and experience `skills`, extract only genuine skills,
technologies, tools, frameworks, programming languages, databases,
platforms, methodologies, professional competencies, or clearly
established domain expertise.

Do NOT treat every noun in the project or experience description
as a skill.

Do NOT extract ordinary business entities or objects such as:
customers, vendors, users, clients, products, invoices, reports,
documents, records, transactions, orders, or accounts.

For example:

"Master Data Creation for Customers, Vendors, Financial Dimensions."

should produce:

["Master Data Creation"]

and should NOT produce:

["customers", "vendors", "financial dimensions", "master data creation"]

Another example:

"Built a Django application using PostgreSQL, Redis and Docker."

should produce:

["Django", "PostgreSQL", "Redis", "Docker"]

and should NOT produce:

["application", "users", "data"]

When uncertain whether something is a genuine skill or merely
a business noun/entity, prefer NOT extracting it.

The goal is high-precision skill extraction.

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