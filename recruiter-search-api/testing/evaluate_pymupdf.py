import json
import re
from pathlib import Path
from difflib import SequenceMatcher

from ingestion.postgresql.extractor import extract_text

ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_PATH = ROOT / "testing" / "ground_truth.json"

TARGET_RESUMES = [
    "ABHISHEK_MITTAL",
    "ABHISHEK_PREMKUMAR_SAWALE",
    "ADITI_JAIN",
    "ADITYA_BELE",
    "ADITYA_DALVI",
]


def normalize(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9+#.\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(
        None,
        normalize(a),
        normalize(b),
    ).ratio()


def exact_match(value: str, extracted_text: str) -> bool:
    value = normalize(value)
    extracted_text = normalize(extracted_text)

    if not value:
        return False

    return value in extracted_text


def fuzzy_match(
    value: str,
    extracted_text: str,
    threshold: float = 0.85,
) -> bool:
    value = normalize(value)

    if not value:
        return False

    extracted_text = normalize(extracted_text)

    if value in extracted_text:
        return True

    words = value.split()

    if len(words) <= 2:
        return similarity(value, extracted_text) >= threshold

    window_size = len(words)

    extracted_words = extracted_text.split()

    for i in range(
        max(1, len(extracted_words) - window_size + 1)
    ):
        window = " ".join(
            extracted_words[i:i + window_size]
        )

        if similarity(value, window) >= threshold:
            return True

    return False


def get_string_values(value):
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        values = []

        for item in value:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                for field in [
                    "company",
                    "title",
                    "name",
                    "skill",
                    "text",
                    "institution",
                    "degree",
                ]:
                    if item.get(field):
                        values.append(
                            str(item[field])
                        )

        return values

    if isinstance(value, dict):
        values = []

        for field in [
            "company",
            "title",
            "name",
            "skill",
            "text",
            "institution",
            "degree",
        ]:
            if value.get(field):
                values.append(
                    str(value[field])
                )

        return values

    return []


def collect_fields(ground_truth):
    fields = {
        "name": [],
        "email": [],
        "phone": [],
        "companies": [],
        "titles": [],
        "skills": [],
        "education": [],
        "projects": [],
    }

    if ground_truth.get("name"):
        fields["name"].append(
            ground_truth["name"]
        )

    if ground_truth.get("email"):
        fields["email"].append(
            ground_truth["email"]
        )

    if ground_truth.get("phone"):
        fields["phone"].append(
            ground_truth["phone"]
        )

    experiences = ground_truth.get(
        "experiences",
        []
    )

    for experience in experiences:
        if experience.get("company"):
            fields["companies"].append(
                experience["company"]
            )

        if experience.get("title"):
            fields["titles"].append(
                experience["title"]
            )

        fields["skills"].extend(
            get_string_values(
                experience.get("skills")
            )
        )

    fields["skills"].extend(
        get_string_values(
            ground_truth.get("skills")
        )
    )

    fields["education"].extend(
        get_string_values(
            ground_truth.get("education")
        )
    )

    fields["projects"].extend(
        get_string_values(
            ground_truth.get("projects")
        )
    )

    return fields


def evaluate_field(
    values,
    extracted_text,
):
    if not values:
        return {
            "expected": 0,
            "exact_matches": 0,
            "fuzzy_matches": 0,
            "exact_coverage": 100.0,
            "fuzzy_coverage": 100.0,
        }

    exact_matches = 0
    fuzzy_matches = 0

    for value in values:
        if exact_match(
            value,
            extracted_text,
        ):
            exact_matches += 1

        if fuzzy_match(
            value,
            extracted_text,
        ):
            fuzzy_matches += 1

    return {
        "expected": len(values),
        "exact_matches": exact_matches,
        "fuzzy_matches": fuzzy_matches,
        "exact_coverage": (
            exact_matches / len(values) * 100
        ),
        "fuzzy_coverage": (
            fuzzy_matches / len(values) * 100
        ),
    }


def evaluate_resume(
    resume_path,
    ground_truth,
):
    extracted_text = extract_text(
        resume_path
    )

    fields = collect_fields(
        ground_truth
    )

    results = {}

    for field_name, values in fields.items():
        results[field_name] = evaluate_field(
            values,
            extracted_text,
        )

    return extracted_text, results


def find_resume(
    resume_directory,
    identifier,
):
    matches = []

    for path in resume_directory.rglob("*.pdf"):
        normalized_name = normalize(
            path.stem
        ).replace(" ", "_")

        normalized_identifier = normalize(
            identifier
        ).replace(" ", "_")

        if normalized_identifier in normalized_name:
            matches.append(path)

    if not matches:
        return None

    return matches[0]


def print_field_result(
    field_name,
    result,
):
    if result["expected"] == 0:
        return

    print(
        f"    {field_name:<12} "
        f"{result['exact_coverage']:>6.1f}% exact | "
        f"{result['fuzzy_coverage']:>6.1f}% fuzzy "
        f"({result['fuzzy_matches']}/"
        f"{result['expected']})"
    )


def main():
    with open(
        GROUND_TRUTH_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        ground_truth = json.load(file)

    resume_directory = ROOT

    all_results = []

    print(
        "\nPyMuPDF Extraction Evaluation"
    )
    print("=" * 70)

    for index, identifier in enumerate(
        TARGET_RESUMES,
        start=1,
    ):
        print(
            f"\n[{index}/5] {identifier}"
        )

        ground_truth_entry = None

        if isinstance(ground_truth, list):
            for entry in ground_truth:
                entry_name = str(
                    entry.get("name", "")
                )

                if normalize(
                    entry_name
                ).replace(" ", "_") == normalize(
                    identifier
                ).replace(" ", "_"):
                    ground_truth_entry = entry
                    break

        elif isinstance(ground_truth, dict):
            ground_truth_entry = (
                ground_truth.get(identifier)
            )

        if ground_truth_entry is None:
            print(
                "  Ground truth entry not found"
            )
            continue

        resume_path = find_resume(
            resume_directory,
            identifier,
        )

        if resume_path is None:
            print(
                "  Resume PDF not found"
            )
            continue

        print(
            f"  File: {resume_path.name}"
        )

        extracted_text, results = (
            evaluate_resume(
                resume_path,
                ground_truth_entry,
            )
        )

        for field_name, result in results.items():
            print_field_result(
                field_name,
                result,
            )

        total_expected = 0
        total_exact = 0
        total_fuzzy = 0

        for result in results.values():
            total_expected += result["expected"]
            total_exact += result["exact_matches"]
            total_fuzzy += result["fuzzy_matches"]

        exact_coverage = (
            total_exact / total_expected * 100
            if total_expected
            else 100
        )

        fuzzy_coverage = (
            total_fuzzy / total_expected * 100
            if total_expected
            else 100
        )

        print(
            f"  Overall: "
            f"{exact_coverage:.1f}% exact | "
            f"{fuzzy_coverage:.1f}% fuzzy"
        )

        all_results.append({
            "resume": identifier,
            "exact_coverage": exact_coverage,
            "fuzzy_coverage": fuzzy_coverage,
            "fields": results,
        })

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if all_results:
        average_exact = sum(
            result["exact_coverage"]
            for result in all_results
        ) / len(all_results)

        average_fuzzy = sum(
            result["fuzzy_coverage"]
            for result in all_results
        ) / len(all_results)

        print(
            f"Average exact coverage: "
            f"{average_exact:.2f}%"
        )

        print(
            f"Average fuzzy coverage: "
            f"{average_fuzzy:.2f}%"
        )


if __name__ == "__main__":
    main()