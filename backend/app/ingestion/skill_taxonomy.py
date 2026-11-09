# app/ingestion/skill_taxonomy.py

"""
Deterministic skill taxonomy.

Purpose:
- Resolve common skill aliases to canonical names.
- Provide stable metadata for known skills.
- Do NOT use an LLM here.
- Unknown skills intentionally return no metadata.
"""

from typing import TypedDict


class SkillMetadata(TypedDict):
    canonical_name: str
    skill_type: str
    description: str


# ============================================================
# Canonical skill metadata
# ============================================================

SKILL_TAXONOMY: dict[str, SkillMetadata] = {

    # --------------------------------------------------------
    # Programming Languages
    # --------------------------------------------------------

    "python": {
        "canonical_name": "Python",
        "skill_type": "Programming Language",
        "description": "A general-purpose programming language.",
    },

    "javascript": {
        "canonical_name": "JavaScript",
        "skill_type": "Programming Language",
        "description": "A programming language commonly used for web development.",
    },

    "typescript": {
        "canonical_name": "TypeScript",
        "skill_type": "Programming Language",
        "description": "A statically typed programming language that extends JavaScript.",
    },

    "java": {
        "canonical_name": "Java",
        "skill_type": "Programming Language",
        "description": "A general-purpose, object-oriented programming language.",
    },

    "c": {
        "canonical_name": "C",
        "skill_type": "Programming Language",
        "description": "A general-purpose procedural programming language.",
    },

    "c++": {
        "canonical_name": "C++",
        "skill_type": "Programming Language",
        "description": "A general-purpose programming language supporting procedural and object-oriented programming.",
    },

    "c#": {
        "canonical_name": "C#",
        "skill_type": "Programming Language",
        "description": "A general-purpose programming language developed by Microsoft.",
    },

    "go": {
        "canonical_name": "Go",
        "skill_type": "Programming Language",
        "description": "A statically typed programming language designed for simplicity and concurrency.",
    },

    "rust": {
        "canonical_name": "Rust",
        "skill_type": "Programming Language",
        "description": "A systems programming language focused on safety and performance.",
    },

    "php": {
        "canonical_name": "PHP",
        "skill_type": "Programming Language",
        "description": "A scripting language widely used for server-side web development.",
    },

    "ruby": {
        "canonical_name": "Ruby",
        "skill_type": "Programming Language",
        "description": "A dynamic, object-oriented programming language.",
    },

    # --------------------------------------------------------
    # Frontend
    # --------------------------------------------------------

    "react": {
        "canonical_name": "React",
        "skill_type": "Frontend Framework",
        "description": "A JavaScript library for building component-based user interfaces.",
    },

    "next.js": {
        "canonical_name": "Next.js",
        "skill_type": "Frontend Framework",
        "description": "A React framework for building full-stack web applications.",
    },

    "angular": {
        "canonical_name": "Angular",
        "skill_type": "Frontend Framework",
        "description": "A TypeScript-based framework for building web applications.",
    },

    "vue": {
        "canonical_name": "Vue.js",
        "skill_type": "Frontend Framework",
        "description": "A JavaScript framework for building user interfaces.",
    },

    "html": {
        "canonical_name": "HTML",
        "skill_type": "Frontend Technology",
        "description": "The standard markup language used to structure web pages.",
    },

    "css": {
        "canonical_name": "CSS",
        "skill_type": "Frontend Technology",
        "description": "A stylesheet language used to define the presentation of web pages.",
    },

    "tailwind css": {
        "canonical_name": "Tailwind CSS",
        "skill_type": "CSS Framework",
        "description": "A utility-first CSS framework for building user interfaces.",
    },

    "bootstrap": {
        "canonical_name": "Bootstrap",
        "skill_type": "CSS Framework",
        "description": "A frontend framework providing reusable UI components and styling utilities.",
    },

    # --------------------------------------------------------
    # Backend
    # --------------------------------------------------------

    "node.js": {
        "canonical_name": "Node.js",
        "skill_type": "Backend Runtime",
        "description": "A JavaScript runtime used for server-side application development.",
    },

    "express.js": {
        "canonical_name": "Express.js",
        "skill_type": "Backend Framework",
        "description": "A lightweight web framework for Node.js applications.",
    },

    "fastapi": {
        "canonical_name": "FastAPI",
        "skill_type": "Backend Framework",
        "description": "A Python web framework for building APIs.",
    },

    "django": {
        "canonical_name": "Django",
        "skill_type": "Backend Framework",
        "description": "A Python web framework for building web applications.",
    },

    "flask": {
        "canonical_name": "Flask",
        "skill_type": "Backend Framework",
        "description": "A lightweight Python web framework.",
    },

    # --------------------------------------------------------
    # Databases
    # --------------------------------------------------------

    "postgresql": {
        "canonical_name": "PostgreSQL",
        "skill_type": "Database",
        "description": "An open-source relational database management system.",
    },

    "mysql": {
        "canonical_name": "MySQL",
        "skill_type": "Database",
        "description": "An open-source relational database management system.",
    },

    "mongodb": {
        "canonical_name": "MongoDB",
        "skill_type": "Database",
        "description": "A document-oriented NoSQL database.",
    },

    "redis": {
        "canonical_name": "Redis",
        "skill_type": "Database / Cache",
        "description": "An in-memory data store commonly used for caching and real-time applications.",
    },

    "sql": {
        "canonical_name": "SQL",
        "skill_type": "Database Query Language",
        "description": "A language used to query and manage relational databases.",
    },

    # --------------------------------------------------------
    # DevOps / Cloud
    # --------------------------------------------------------

    "docker": {
        "canonical_name": "Docker",
        "skill_type": "DevOps / Containerization",
        "description": "A platform for packaging and running applications in containers.",
    },

    "kubernetes": {
        "canonical_name": "Kubernetes",
        "skill_type": "DevOps / Container Orchestration",
        "description": "An open-source platform for orchestrating containerized applications.",
    },

    "git": {
        "canonical_name": "Git",
        "skill_type": "Version Control",
        "description": "A distributed version control system.",
    },

    "github": {
        "canonical_name": "GitHub",
        "skill_type": "Developer Platform",
        "description": "A platform for hosting Git repositories and collaborating on software development.",
    },

    "gitlab": {
        "canonical_name": "GitLab",
        "skill_type": "Developer Platform",
        "description": "A platform for source code management and DevOps workflows.",
    },

    "jenkins": {
        "canonical_name": "Jenkins",
        "skill_type": "CI/CD",
        "description": "An automation server commonly used to implement continuous integration and delivery pipelines.",
    },

    "aws": {
        "canonical_name": "AWS",
        "skill_type": "Cloud Platform",
        "description": "A cloud computing platform providing infrastructure and application services.",
    },

    "azure": {
        "canonical_name": "Microsoft Azure",
        "skill_type": "Cloud Platform",
        "description": "A cloud computing platform provided by Microsoft.",
    },

    "google cloud": {
        "canonical_name": "Google Cloud",
        "skill_type": "Cloud Platform",
        "description": "A cloud computing platform provided by Google.",
    },

    # --------------------------------------------------------
    # APIs / Architecture
    # --------------------------------------------------------

    "rest api": {
        "canonical_name": "REST API",
        "skill_type": "API / Web Services",
        "description": "An architectural approach for building web APIs using HTTP.",
    },

    "graphql": {
        "canonical_name": "GraphQL",
        "skill_type": "API Technology",
        "description": "A query language and runtime for APIs.",
    },

    # --------------------------------------------------------
    # AI / ML
    # --------------------------------------------------------

    "machine learning": {
        "canonical_name": "Machine Learning",
        "skill_type": "Artificial Intelligence",
        "description": "A field of artificial intelligence focused on learning patterns from data.",
    },

    "deep learning": {
        "canonical_name": "Deep Learning",
        "skill_type": "Artificial Intelligence",
        "description": "A branch of machine learning based on multi-layer neural networks.",
    },

    "tensorflow": {
        "canonical_name": "TensorFlow",
        "skill_type": "Machine Learning Framework",
        "description": "An open-source framework for machine learning and deep learning.",
    },

    "pytorch": {
        "canonical_name": "PyTorch",
        "skill_type": "Machine Learning Framework",
        "description": "An open-source machine learning framework used for deep learning.",
    },

    "scikit-learn": {
        "canonical_name": "scikit-learn",
        "skill_type": "Machine Learning Library",
        "description": "A Python library providing machine learning algorithms and utilities.",
    },

    "langchain": {
        "canonical_name": "LangChain",
        "skill_type": "AI / LLM Framework",
        "description": "A framework for building applications powered by large language models.",
    },

    "qdrant": {
        "canonical_name": "Qdrant",
        "skill_type": "Vector Database",
        "description": "A vector database designed for similarity search and AI applications.",
    },

    # --------------------------------------------------------
    # Data / Python ecosystem
    # --------------------------------------------------------

    "numpy": {
        "canonical_name": "NumPy",
        "skill_type": "Data Science Library",
        "description": "A Python library for numerical computing and array operations.",
    },

    "pandas": {
        "canonical_name": "Pandas",
        "skill_type": "Data Science Library",
        "description": "A Python library for data manipulation and analysis.",
    },
}


# ============================================================
# Aliases
# ============================================================

SKILL_ALIASES: dict[str, str] = {

    # Python
    "python3": "python",
    "python 3": "python",

    # JavaScript
    "js": "javascript",
    "javascript es6": "javascript",

    # TypeScript
    "ts": "typescript",

    # React
    "reactjs": "react",
    "react js": "react",
    "react.js": "react",

    # Next
    "nextjs": "next.js",
    "next js": "next.js",

    # Angular
    "angularjs": "angular",

    # Vue
    "vuejs": "vue",
    "vue.js": "vue",

    # Node
    "nodejs": "node.js",
    "node js": "node.js",

    # Express
    "express": "express.js",
    "expressjs": "express.js",

    # PostgreSQL
    "postgres": "postgresql",
    "postgres db": "postgresql",
    "postgres database": "postgresql",
    "postgres sql": "postgresql",

    # Mongo
    "mongo": "mongodb",
    "mongo db": "mongodb",

    # REST
    "rest": "rest api",
    "restful api": "rest api",
    "rest apis": "rest api",

    # Tailwind
    "tailwind": "tailwind css",
    "tailwindcss": "tailwind css",

    # GitHub
    "github.com": "github",

    # AWS
    "amazon web services": "aws",

    # GCP
    "gcp": "google cloud",
    "google cloud platform": "google cloud",

    # Machine learning
    "ml": "machine learning",

    # Deep learning
    "dl": "deep learning",

    # Scikit
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",

    # NumPy
    "numpy library": "numpy",

    # Pandas
    "pandas library": "pandas",
}


# ============================================================
# Helpers
# ============================================================

def _normalize_lookup_name(name: str) -> str:
    """
    Normalize a skill name for taxonomy lookup.

    This intentionally stays simple and deterministic.
    """
    return " ".join(
        name.lower().strip().split()
    )


def resolve_skill_name(name: str) -> str:
    """
    Resolve a raw skill name to its canonical normalized name.

    Unknown skills are returned in normalized form.
    """

    normalized = _normalize_lookup_name(name)

    canonical_key = SKILL_ALIASES.get(
        normalized,
        normalized,
    )

    return canonical_key


def get_skill_metadata(
    name: str,
) -> tuple[str, str | None, str | None]:
    """
    Return:

        canonical_name,
        skill_type,
        description

    Unknown skills return:

        normalized_name,
        None,
        None
    """

    normalized = resolve_skill_name(name)

    metadata = SKILL_TAXONOMY.get(normalized)

    if metadata is None:
        return (
            normalized,
            None,
            None,
        )

    return (
        metadata["canonical_name"],
        metadata["skill_type"],
        metadata["description"],
    )