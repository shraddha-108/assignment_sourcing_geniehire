from datetime import date

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


load_dotenv()


MODEL = "gpt-4o-mini"


class Experience(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    duration_months: int = 0
    skills: list[str] = Field(default_factory=list)
    evidence: str = ""


class Project(BaseModel):
    title: str = ""
    evidence: str = ""


class EvidenceSections(BaseModel):
    summary: str = ""
    experience: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class ResumeData(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None

    experiences: list[Experience] = Field(
        default_factory=list
    )

    skills: list[str] = Field(
        default_factory=list
    )

    evidence: EvidenceSections = Field(
        default_factory=EvidenceSections
    )


SYSTEM_PROMPT = """
You are a professional resume information extraction system.

Your task is to extract structured information from a resume
without inventing, guessing, summarizing, or changing factual content.

The resume text provided to you is the source of truth.

GENERAL RULES:

1. Extract only information explicitly supported by the resume.

2. Never invent, guess, infer, or fabricate information.

3. If information is absent or genuinely unavailable, return null
   or an empty list.

4. Preserve the original wording of resume evidence.

5. Evidence is NOT a summary.

6. Evidence is NOT a paraphrase.

7. Evidence is NOT a rewritten version of the resume.

8. Evidence must contain the actual wording from the resume as closely
   as possible.

9. Do not combine unrelated sections.

10. Do not move information between sections simply because the
    information contains similar skills or technologies.


CANDIDATE:

11. Extract the actual person's name.

12. Never use an email address, URL, company name, job title,
    project name, skill, section heading, or ordinary sentence
    as the person's name.

13. Extract email and phone only when explicitly present.


EMPLOYMENT EXPERIENCE:

14. Extract actual employment or professional work experiences.

15. Do not treat projects, education, certifications, courses,
    achievements, internships, positions of responsibility,
    volunteering, or extracurricular activities as employment
    unless the resume explicitly presents them as employment/work.

16. Preserve separate employment roles when multiple roles exist
    at the same company.

17. Extract company and job title from the actual employment heading.

18. Extract employment dates directly from the employment heading
    associated with that role.

19. Never derive employment dates from project dates.

20. Never derive employment dates from education dates.

21. Never derive employment dates from certification dates.

22. Never derive employment dates from unrelated numbers in the resume.

23. If the resume says Present or Current, use null for end_date.

24. If only month and year are available, use the first day of that month.

25. Examples:

    July 2025 -> 2025-07-01
    March 2023 -> 2023-03-01

26. Never create an employment date that does not correspond
    to a date shown in the resume.

27. If an employment date cannot be confidently identified,
    return null.


EXPERIENCE EVIDENCE:

28. For every employment experience, the evidence field must contain
    the original resume text describing that employment.

29. Include the important responsibilities, technologies,
    accomplishments, and work performed for that role.

30. Preserve the original wording.

31. Do not summarize the responsibilities.

32. Do not rewrite the responsibilities.

33. Do not generate new sentences.

34. Do not include unrelated project descriptions in employment evidence.

35. If the employment section contains multiple bullet points,
    preserve the relevant bullet points belonging to that role.

36. Evidence should be sufficient for semantic retrieval of what
    the candidate actually worked on.


PROJECT EXTRACTION:

37. Projects are a separate category from employment.

38. Look for project sections using headings such as:

    Projects
    Project
    Personal Projects
    Academic Projects
    Professional Projects
    Project Experience
    Selected Projects
    Relevant Projects
    Key Projects
    Major Projects
    Portfolio Projects

39. Resume headings may use different wording.

40. If a clearly identifiable project section exists, extract
    every project contained in that section.

41. Each project MUST be returned as one Project object.

42. The project title MUST contain the actual project title
    exactly as written in the resume whenever possible.

43. The project evidence MUST contain the original project text
    belonging to that project.

44. Project evidence must include the project's technologies,
    tools, responsibilities, implementation details,
    achievements, and bullet points when present.

45. Preserve the original wording.

46. Do not summarize project descriptions.

47. Do not paraphrase project descriptions.

48. Do not rewrite project descriptions.

49. Do not generate project descriptions from your own knowledge.

50. Do not move project descriptions into employment evidence.

51. A project must remain a project even when it contains
    technologies that are also used in employment.

52. Do not split one project's bullets into multiple projects.

53. Do not combine multiple separate projects into one project.

54. If a project has a title followed by multiple bullets,
    all of those bullets belong to the same project evidence.

55. If the project has technologies listed directly below
    the title, preserve those technologies in the project evidence.

56. If the resume contains a Projects section with identifiable
    project content, the projects list MUST NOT be empty.

57. If the resume contains no project content, return an empty list.

58. Do not create fictional projects.


SUMMARY:

59. Identify the resume's summary/profile section.

60. Summary headings may include:

    Summary
    Professional Summary
    Profile
    Career Summary
    Career Snapshot
    Professional Profile
    About Me
    Objective

61. If a summary/profile section exists, preserve its original text.

62. Do not create a summary when the resume does not contain one.

63. Do not rewrite or improve the summary.

64. Do not combine the summary with employment or project content.


SKILLS:

65. Extract all explicitly mentioned skills from the entire resume.

66. Skills are not limited to a section named Skills.

67. Look under headings such as:

    Skills
    Technical Skills
    Technical Expertise
    Core Skills
    Core Competencies
    Key Skills
    Expertise
    Technologies
    Tools
    Additional Information
    Professional Summary
    Profile
    Areas of Expertise
    Soft Skills
    Competencies

68. Extract both technical and soft skills when explicitly listed.

69. Preserve meaningful multi-word skills.

70. Normalize only obvious aliases:

    JS -> JavaScript
    TS -> TypeScript
    React.js -> React
    ReactJS -> React
    Mongo DB -> MongoDB
    ML -> Machine Learning
    DL -> Deep Learning

71. Do not turn ordinary nouns or resume words into skills unless
    the resume clearly presents them as skills, technologies,
    expertise, competencies, or capabilities.

72. For every employment experience, include only skills explicitly
    supported by that employment.

73. Do not copy the entire general skills list into every employment.

74. A skill appearing only in a general skills section does not prove
    that it was used during employment.

75. If a skill appears in an employment responsibility, technology,
    implementation, or work description, associate it with that
    employment experience.


OTHER RESUME SECTIONS:

76. Preserve important content under unusual headings.

77. Achievements, awards, honors, academic achievements, and
    accomplishments should go into achievements.

78. Education and academic qualifications should go into education.

79. Certifications, courses, positions of responsibility,
    extracurricular activities, and other relevant sections should
    go into other unless they clearly belong elsewhere.

80. Do not discard meaningful resume content merely because
    the heading is unfamiliar.

81. Do not move project or employment content into other.


EVIDENCE FIDELITY:

82. The following three evidence categories are especially important:

    summary
    experience
    projects

83. These categories are intended for semantic retrieval.

84. Their text must be grounded in the original resume.

85. Do not use your own wording for these fields.

86. Do not compress multiple bullets into a generated sentence.

87. Do not convert detailed evidence into a short summary.

88. Preserve important technical terms, technologies,
    responsibilities, project names, and implementation details.

89. If the resume contains a section heading and several bullets,
    preserve the meaningful content belonging to that section.

90. Do not remove technical details merely because they seem repetitive.


CALCULATIONS:

91. Do not calculate total experience months.

92. Do not calculate skill experience months.

93. Do not calculate last-used dates.

94. Do not calculate employment duration months.

95. These values will be calculated separately by Python.


FINAL VALIDATION:

96. Did you extract the actual person's name?

97. Did you extract all actual employment experiences?

98. Did you read employment dates from the employment headings?

99. Did you preserve employment evidence?

100. Did you identify a Summary/Profile section if one exists?

101. Did you preserve the summary text instead of generating a summary?

102. Did you identify a Projects section if one exists?

103. Did you extract every identifiable project?

104. Does every project have its own Project object?

105. Does every project object have the correct project title?

106. Does every project preserve its original description?

107. Did you keep separate projects separate?

108. Did you keep projects separate from employment?

109. Did you preserve original evidence rather than paraphrasing?

110. Did you extract skills appearing anywhere in the resume?

111. Did you avoid inventing information?

112. If the resume clearly contains projects, is the projects list
     populated rather than incorrectly returning an empty list?
"""


llm = ChatOpenAI(
    model=MODEL,
    temperature=0,
)


structured_llm = llm.with_structured_output(
    ResumeData
)


def validate_experience_dates(
    experiences: list[Experience],
) -> None:

    current_year = date.today().year

    for experience in experiences:

        if experience.start_date:

            if (
                experience.start_date.year < 1950
                or experience.start_date.year > current_year + 1
            ):
                experience.start_date = None

        if experience.end_date:

            if (
                experience.end_date.year < 1950
                or experience.end_date.year > current_year + 1
            ):
                experience.end_date = None

        if (
            experience.start_date
            and experience.end_date
            and experience.end_date < experience.start_date
        ):
            experience.start_date = None
            experience.end_date = None


def calculate_months(
    start_date: date,
    end_date: date,
) -> int:

    if end_date < start_date:
        return 0

    return max(
        (
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
        ),
        0,
    )


def calculate_experience_duration(
    experience: Experience,
) -> int:

    if not experience.start_date:
        return 0

    end_date = experience.end_date or date.today()

    if end_date < experience.start_date:
        return 0

    return calculate_months(
        start_date=experience.start_date,
        end_date=end_date,
    )


def merge_date_ranges(
    ranges: list[tuple[date, date]],
) -> list[tuple[date, date]]:

    if not ranges:
        return []

    sorted_ranges = sorted(
        ranges,
        key=lambda item: item[0],
    )

    merged = [sorted_ranges[0]]

    for current_start, current_end in sorted_ranges[1:]:

        previous_start, previous_end = merged[-1]

        if current_start <= previous_end:

            merged[-1] = (
                previous_start,
                max(previous_end, current_end),
            )

        else:

            merged.append(
                (
                    current_start,
                    current_end,
                )
            )

    return merged


def calculate_total_experience_months(
    experiences: list[Experience],
) -> int:

    ranges = []

    today = date.today()

    for experience in experiences:

        if not experience.start_date:
            continue

        end_date = experience.end_date or today

        if end_date < experience.start_date:
            continue

        ranges.append(
            (
                experience.start_date,
                end_date,
            )
        )

    merged_ranges = merge_date_ranges(ranges)

    return sum(
        calculate_months(
            start_date=start_date,
            end_date=end_date,
        )
        for start_date, end_date in merged_ranges
    )


def calculate_skill_records(
    experiences: list[Experience],
    skills: list[str],
) -> list[dict]:

    skill_ranges: dict[
        str,
        list[tuple[date, date]],
    ] = {
        skill: []
        for skill in skills
    }

    today = date.today()

    for experience in experiences:

        if not experience.start_date:
            continue

        end_date = experience.end_date or today

        if end_date < experience.start_date:
            continue

        for skill in experience.skills:

            if skill not in skill_ranges:
                skill_ranges[skill] = []

            skill_ranges[skill].append(
                (
                    experience.start_date,
                    end_date,
                )
            )

    records = []

    for skill in sorted(skill_ranges):

        ranges = merge_date_ranges(
            skill_ranges[skill]
        )

        total_months = sum(
            calculate_months(
                start_date=start_date,
                end_date=end_date,
            )
            for start_date, end_date in ranges
        )

        last_used_date = None

        if ranges:

            last_used_date = max(
                end_date
                for _, end_date in ranges
            )

        records.append(
            {
                "skill": skill,
                "last_used_date": last_used_date,
                "total_months": total_months,
            }
        )

    return records


def parse_resume_with_llm(
    text: str,
) -> dict:

    prompt = f"""
Extract structured information from the following resume.

The resume text is the ONLY source of truth.

CRITICAL EVIDENCE REQUIREMENT:

For summary, employment evidence, and projects:

- Preserve the original resume wording.
- Do not summarize.
- Do not paraphrase.
- Do not rewrite.
- Do not invent sentences.
- Do not combine unrelated sections.

PROJECT EXTRACTION IS CRITICAL.

If the resume contains a Projects, Personal Projects,
Academic Projects, Project Experience, Selected Projects,
Relevant Projects, or similar section:

1. Find every identifiable project.

2. Create ONE Project object for EACH project.

3. Put the exact project title in the title field.

4. Put the complete original project description in the evidence field.

5. Include all bullets belonging to that project.

6. Include technologies and implementation details belonging
   to that project.

7. Do NOT split one project into multiple projects.

8. Do NOT merge separate projects.

9. Do NOT move project content into employment.

10. Do NOT return an empty projects list when project content
    clearly exists.

For employment:

- Identify the exact company.
- Identify the exact job title.
- Read dates directly from the employment heading.
- Preserve the actual work-description bullets as evidence.
- Include only skills supported by that employment.
- Do not calculate employment duration. Python will calculate it.

For summary:

- If a summary/profile exists, preserve its actual text.
- Do not generate a new summary.

For skills:

- Extract explicitly mentioned skills from the entire resume.
- Include skills from non-standard sections.
- Do not copy general skills into employment experiences unless
  the employment text supports their use.

RESUME:

{text}
"""

    parsed = structured_llm.invoke(
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

    if parsed is None:
        raise ValueError(
            "LLM returned no parsed resume data."
        )

    validate_experience_dates(
        parsed.experiences
    )

    for experience in parsed.experiences:
        experience.duration_months = (
            calculate_experience_duration(
                experience
            )
        )

    total_experience_months = (
        calculate_total_experience_months(
            parsed.experiences
        )
    )

    skill_records = calculate_skill_records(
        experiences=parsed.experiences,
        skills=parsed.skills,
    )

    return {
        "name": parsed.name,
        "email": parsed.email,
        "phone": parsed.phone,

        "experiences": [
            {
                "company": experience.company,
                "title": experience.title,
                "start_date": experience.start_date,
                "end_date": experience.end_date,
                "duration_months": experience.duration_months,
                "skills": experience.skills,
                "evidence": experience.evidence,
            }
            for experience in parsed.experiences
        ],

        "skills": skill_records,

        "total_experience_months": (
            total_experience_months
        ),

        "evidence": {
            "summary": parsed.evidence.summary,

            "experience": parsed.evidence.experience,

            "projects": [
                {
                    "title": project.title,
                    "evidence": project.evidence,
                }
                for project in parsed.evidence.projects
            ],

            "achievements": parsed.evidence.achievements,

            "education": parsed.evidence.education,

            "other": parsed.evidence.other,
        },
    }