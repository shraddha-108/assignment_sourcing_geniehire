import json
import re
from datetime import date
from pathlib import Path
from difflib import SequenceMatcher

from ingestion.postgresql.extractor import extract_text
from ingestion.postgresql.llm_parser import parse_resume_with_llm


BASE_DIR = Path(__file__).resolve().parents[1]

GROUND_TRUTH_PATH = BASE_DIR / "testing" / "ground_truth.json"
RESUME_DIR = BASE_DIR / "data"
RESULT_PATH = BASE_DIR / "testing" / "llm_evaluation_results.json"


def normalize_text(value):
    if value is None:
        return ""

    value = str(value).lower().strip()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(value.split())


def normalize_email(value):
    if not value:
        return ""

    return value.lower().strip()


def normalize_phone(value):
    if not value:
        return ""

    return re.sub(
        r"\D",
        "",
        str(value),
    )


def tokenize(value):
    return set(
        normalize_text(value).split()
    )


def similarity(value1, value2):
    value1 = normalize_text(value1)
    value2 = normalize_text(value2)

    if not value1 or not value2:
        return 0.0

    return SequenceMatcher(
        None,
        value1,
        value2,
    ).ratio()


def text_similarity(
    predicted,
    actual,
):
    predicted_tokens = tokenize(predicted)
    actual_tokens = tokenize(actual)

    if not predicted_tokens or not actual_tokens:
        return (
            1.0
            if not predicted and not actual
            else 0.0
        )

    intersection = (
        predicted_tokens.intersection(
            actual_tokens
        )
    )

    precision = (
        len(intersection)
        / len(predicted_tokens)
    )

    recall = (
        len(intersection)
        / len(actual_tokens)
    )

    if precision + recall:
        token_f1 = (
            2 * precision * recall
            / (precision + recall)
        )
    else:
        token_f1 = 0.0

    sequence_score = similarity(
        predicted,
        actual,
    )

    return (
        token_f1 * 0.7
        + sequence_score * 0.3
    )


def calculate_precision_recall_f1(
    predicted,
    actual,
):
    predicted = set(predicted)
    actual = set(actual)

    true_positive = len(
        predicted.intersection(actual)
    )

    if predicted:
        precision = (
            true_positive / len(predicted)
        )
    else:
        precision = (
            1.0
            if not actual
            else 0.0
        )

    if actual:
        recall = (
            true_positive / len(actual)
        )
    else:
        recall = (
            1.0
            if not predicted
            else 0.0
        )

    if precision + recall:
        f1 = (
            2 * precision * recall
            / (precision + recall)
        )
    else:
        f1 = 0.0

    return {
        "precision": round(
            precision,
            4,
        ),
        "recall": round(
            recall,
            4,
        ),
        "f1": round(
            f1,
            4,
        ),
    }


def normalize_skill(skill):
    skill = normalize_text(skill)

    aliases = {
        "fastapi": "fast api",
        "reactjs": "react",
        "react js": "react",
        "nodejs": "node js",
        "node js": "node js",
        "postgres": "postgresql",
        "mongo db": "mongodb",
        "js": "javascript",
        "ts": "typescript",
        "ml": "machine learning",
        "dl": "deep learning",
    }

    return aliases.get(
        skill,
        skill,
    )


def skill_metrics(
    predicted_skills,
    actual_skills,
):
    predicted = {
        normalize_skill(
            skill["skill"]
        )
        for skill in predicted_skills
    }

    actual = {
        normalize_skill(skill)
        for skill in actual_skills
    }

    return calculate_precision_recall_f1(
        predicted,
        actual,
    )


def match_experiences(
    predicted_experiences,
    actual_experiences,
):
    unmatched_actual = list(
        range(len(actual_experiences))
    )

    matches = []

    for predicted in predicted_experiences:
        best_match = None
        best_score = 0.0

        for index in unmatched_actual:
            actual = actual_experiences[index]

            company_score = similarity(
                predicted.get("company"),
                actual.get("company"),
            )

            title_score = similarity(
                predicted.get("title"),
                actual.get("title"),
            )

            score = (
                company_score * 0.5
                + title_score * 0.5
            )

            if score > best_score:
                best_score = score
                best_match = index

        if (
            best_match is not None
            and best_score >= 0.75
        ):
            matches.append(
                (
                    predicted,
                    actual_experiences[
                        best_match
                    ],
                    best_score,
                )
            )

            unmatched_actual.remove(
                best_match
            )

    return matches


def date_accuracy(
    predicted_date,
    actual_date,
):
    if predicted_date == actual_date:
        return 1.0

    if (
        predicted_date is None
        or actual_date is None
    ):
        return 0.0

    return (
        1.0
        if str(predicted_date)
        == str(actual_date)
        else 0.0
    )


def experience_metrics(
    predicted_experiences,
    actual_experiences,
):
    matches = match_experiences(
        predicted_experiences,
        actual_experiences,
    )

    predicted_count = len(
        predicted_experiences
    )

    actual_count = len(
        actual_experiences
    )

    matched_count = len(matches)

    if predicted_count:
        precision = (
            matched_count
            / predicted_count
        )
    else:
        precision = (
            1.0
            if actual_count == 0
            else 0.0
        )

    if actual_count:
        recall = (
            matched_count
            / actual_count
        )
    else:
        recall = (
            1.0
            if predicted_count == 0
            else 0.0
        )

    if precision + recall:
        f1 = (
            2 * precision * recall
            / (precision + recall)
        )
    else:
        f1 = 0.0

    date_scores = []

    for predicted, actual, _ in matches:
        start_score = date_accuracy(
            predicted.get("start_date"),
            actual.get("start_date"),
        )

        end_score = date_accuracy(
            predicted.get("end_date"),
            actual.get("end_date"),
        )

        date_scores.extend(
            [
                start_score,
                end_score,
            ]
        )

    if date_scores:
        date_score = (
            sum(date_scores)
            / len(date_scores)
        )
    else:
        date_score = 0.0

    return {
        "predicted_count": predicted_count,
        "actual_count": actual_count,
        "matched_count": matched_count,
        "precision": round(
            precision,
            4,
        ),
        "recall": round(
            recall,
            4,
        ),
        "f1": round(
            f1,
            4,
        ),
        "date_accuracy": round(
            date_score,
            4,
        ),
    }


def calculate_months(
    start_date,
    end_date,
):
    if not start_date:
        return 0

    if end_date is None:
        end_date = date.today()

    if end_date < start_date:
        return 0

    return max(
        (
            (end_date.year - start_date.year)
            * 12
            + end_date.month
            - start_date.month
        ),
        0,
    )


def merge_ranges(ranges):
    if not ranges:
        return []

    ranges = sorted(
        ranges,
        key=lambda item: item[0],
    )

    merged = [ranges[0]]

    for current_start, current_end in ranges[1:]:
        previous_start, previous_end = (
            merged[-1]
        )

        if current_start <= previous_end:
            merged[-1] = (
                previous_start,
                max(
                    previous_end,
                    current_end,
                ),
            )
        else:
            merged.append(
                (
                    current_start,
                    current_end,
                )
            )

    return merged


def calculate_ground_truth_experience(
    experiences,
):
    ranges = []

    for experience in experiences:
        if not experience.get(
            "start_date"
        ):
            continue

        start_date = date.fromisoformat(
            experience["start_date"]
        )

        end_date_value = experience.get(
            "end_date"
        )

        if end_date_value:
            end_date = date.fromisoformat(
                end_date_value
            )
        else:
            end_date = date.today()

        ranges.append(
            (
                start_date,
                end_date,
            )
        )

    merged = merge_ranges(ranges)

    return sum(
        calculate_months(
            start_date,
            end_date,
        )
        for start_date, end_date in merged
    )


def total_experience_accuracy(
    predicted,
    actual,
):
    if predicted == actual:
        return 1.0

    if actual == 0:
        return 0.0

    difference = abs(
        predicted - actual
    )

    if difference <= 1:
        return 0.9

    if difference <= 2:
        return 0.8

    if difference <= 3:
        return 0.7

    return 0.0


def section_item_metrics(
    predicted_items,
    actual_items,
):
    predicted_items = [
        item
        for item in predicted_items
        if normalize_text(item)
    ]

    actual_items = [
        item
        for item in actual_items
        if normalize_text(item)
    ]

    if not predicted_items and not actual_items:
        return {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "predicted_count": 0,
            "actual_count": 0,
            "matched_count": 0,
        }

    if not predicted_items:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "predicted_count": 0,
            "actual_count": len(actual_items),
            "matched_count": 0,
        }

    if not actual_items:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "predicted_count": len(
                predicted_items
            ),
            "actual_count": 0,
            "matched_count": 0,
        }

    unmatched_actual = set(
        range(len(actual_items))
    )

    matched_count = 0
    similarity_scores = []

    for predicted in predicted_items:
        best_index = None
        best_score = 0.0

        for index in unmatched_actual:
            score = text_similarity(
                predicted,
                actual_items[index],
            )

            if score > best_score:
                best_score = score
                best_index = index

        if (
            best_index is not None
            and best_score >= 0.35
        ):
            matched_count += 1
            similarity_scores.append(
                best_score
            )
            unmatched_actual.remove(
                best_index
            )

    precision = (
        matched_count
        / len(predicted_items)
    )

    recall = (
        matched_count
        / len(actual_items)
    )

    if precision + recall:
        f1 = (
            2 * precision * recall
            / (precision + recall)
        )
    else:
        f1 = 0.0

    average_similarity = (
        sum(similarity_scores)
        / len(similarity_scores)
        if similarity_scores
        else 0.0
    )

    return {
        "precision": round(
            precision,
            4,
        ),
        "recall": round(
            recall,
            4,
        ),
        "f1": round(
            f1,
            4,
        ),
        "predicted_count": len(
            predicted_items
        ),
        "actual_count": len(
            actual_items
        ),
        "matched_count": matched_count,
        "average_similarity": round(
            average_similarity,
            4,
        ),
    }


def single_text_metrics(
    predicted,
    actual,
):
    predicted = predicted or ""
    actual = actual or ""

    if not predicted and not actual:
        score = 1.0
    elif not predicted or not actual:
        score = 0.0
    else:
        score = text_similarity(
            predicted,
            actual,
        )

    return {
        "predicted": predicted,
        "actual": actual,
        "score": round(
            score,
            4,
        ),
    }


def evidence_metrics(
    predicted_evidence,
    actual_evidence,
):
    predicted_evidence = (
        predicted_evidence or {}
    )

    actual_evidence = (
        actual_evidence or {}
    )

    return {
        "summary": single_text_metrics(
            predicted_evidence.get(
                "summary",
                "",
            ),
            actual_evidence.get(
                "summary",
                "",
            ),
        ),
        "experience": section_item_metrics(
            predicted_evidence.get(
                "experience",
                [],
            ),
            actual_evidence.get(
                "experience",
                [],
            ),
        ),
        "projects": section_item_metrics(
            predicted_evidence.get(
                "projects",
                [],
            ),
            actual_evidence.get(
                "projects",
                [],
            ),
        ),
        "achievements": section_item_metrics(
            predicted_evidence.get(
                "achievements",
                [],
            ),
            actual_evidence.get(
                "achievements",
                [],
            ),
        ),
        "education": section_item_metrics(
            predicted_evidence.get(
                "education",
                [],
            ),
            actual_evidence.get(
                "education",
                [],
            ),
        ),
    }


def find_matching_resume(
    ground_truth,
    resume_files,
):
    target_name = normalize_text(
        ground_truth.get("name")
    )

    target_resume = normalize_text(
        ground_truth.get("resume")
    )

    if not target_name:
        return None

    exact_matches = []

    for path in resume_files:
        filename = normalize_text(
            path.stem
        )

        if (
            filename.startswith(target_name)
            or target_name.startswith(filename)
            or (
                target_resume
                and filename.startswith(
                    target_resume
                )
            )
        ):
            exact_matches.append(path)

    if len(exact_matches) == 1:
        return exact_matches[0]

    best_file = None
    best_score = 0.0
    second_best_score = 0.0

    target_tokens = set(
        target_name.split()
    )

    for path in resume_files:
        filename = normalize_text(
            path.stem
        )

        filename_tokens = set(
            filename.split()
        )

        if target_tokens:
            token_overlap = (
                len(
                    target_tokens.intersection(
                        filename_tokens
                    )
                )
                / len(target_tokens)
            )
        else:
            token_overlap = 0.0

        text_score = similarity(
            target_name,
            filename,
        )

        score = (
            text_score * 0.5
            + token_overlap * 0.5
        )

        if score > best_score:
            second_best_score = best_score
            best_score = score
            best_file = path
        elif score > second_best_score:
            second_best_score = score

    if (
        best_file is not None
        and best_score >= 0.70
        and (
            best_score - second_best_score
            >= 0.05
        )
    ):
        return best_file

    return None


def evaluate_resume(
    ground_truth,
    pdf_path,
):
    text = extract_text(pdf_path)

    predicted = parse_resume_with_llm(
        text
    )

    name_score = similarity(
        predicted.get("name"),
        ground_truth.get("name"),
    )

    email_score = (
        1.0
        if normalize_email(
            predicted.get("email")
        )
        == normalize_email(
            ground_truth.get("email")
        )
        else 0.0
    )

    phone_score = (
        1.0
        if normalize_phone(
            predicted.get("phone")
        )
        == normalize_phone(
            ground_truth.get("phone")
        )
        else 0.0
    )

    experience_result = experience_metrics(
        predicted.get(
            "experiences",
            [],
        ),
        ground_truth.get(
            "experiences",
            [],
        ),
    )

    skills_result = skill_metrics(
        predicted.get(
            "skills",
            [],
        ),
        ground_truth.get(
            "skills",
            [],
        ),
    )

    expected_total_experience = (
        calculate_ground_truth_experience(
            ground_truth.get(
                "experiences",
                [],
            )
        )
    )

    predicted_total_experience = (
        predicted.get(
            "total_experience_months",
            0,
        )
    )

    total_experience_score = (
        total_experience_accuracy(
            predicted_total_experience,
            expected_total_experience,
        )
    )

    evidence_result = evidence_metrics(
        predicted.get(
            "evidence",
            {},
        ),
        ground_truth.get(
            "evidence",
            {},
        ),
    )

    overall_score = (
        experience_result["f1"] * 0.20
        + experience_result[
            "date_accuracy"
        ] * 0.10
        + skills_result["f1"] * 0.20
        + total_experience_score * 0.10
        + evidence_result[
            "experience"
        ]["f1"] * 0.15
        + evidence_result[
            "projects"
        ]["f1"] * 0.10
        + evidence_result[
            "education"
        ]["f1"] * 0.05
        + evidence_result[
            "summary"
        ]["score"] * 0.05
        + evidence_result[
            "achievements"
        ]["f1"] * 0.03
        + name_score * 0.01
        + email_score * 0.005
        + phone_score * 0.005
    )

    return {
        "resume": ground_truth["resume"],
        "file": pdf_path.name,
        "name": {
            "predicted": predicted.get(
                "name"
            ),
            "actual": ground_truth.get(
                "name"
            ),
            "score": round(
                name_score,
                4,
            ),
        },
        "email": {
            "predicted": predicted.get(
                "email"
            ),
            "actual": ground_truth.get(
                "email"
            ),
            "score": email_score,
        },
        "phone": {
            "predicted": predicted.get(
                "phone"
            ),
            "actual": ground_truth.get(
                "phone"
            ),
            "score": phone_score,
        },
        "experiences": experience_result,
        "skills": skills_result,
        "total_experience": {
            "predicted": (
                predicted_total_experience
            ),
            "actual": (
                expected_total_experience
            ),
            "score": round(
                total_experience_score,
                4,
            ),
        },
        "evidence": evidence_result,
        "overall_score": round(
            overall_score,
            4,
        ),
    }


def print_section_result(
    name,
    result,
):
    if "score" in result:
        print(
            f"{name}: "
            f"{result['score']:.2%}"
        )
    else:
        print(
            f"{name} F1: "
            f"{result['f1']:.2%}"
        )


def main():
    with open(
        GROUND_TRUTH_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        ground_truth = json.load(
            file
        )

    resume_files = sorted(
        [
            path
            for path in RESUME_DIR.iterdir()
            if path.suffix.lower()
            == ".pdf"
        ],
        key=lambda path: path.name.lower(),
    )

    print(
        f"Found {len(resume_files)} PDF files"
    )

    print(
        f"Ground truth entries: "
        f"{len(ground_truth)}"
    )

    print()

    results = []

    for index, item in enumerate(
        ground_truth,
        start=1,
    ):
        resume_name = item["resume"]

        pdf_path = find_matching_resume(
            item,
            resume_files,
        )

        print(
            f"[{index}/{len(ground_truth)}] "
            f"{resume_name}"
        )

        if pdf_path is None:
            print(
                "  SKIPPED: "
                "Could not confidently "
                "match PDF"
            )
            print()
            continue

        print(
            f"  File: {pdf_path.name}"
        )

        result = evaluate_resume(
            item,
            pdf_path,
        )

        results.append(result)

        print(
            f"  Experience F1: "
            f"{result['experiences']['f1']:.2%}"
        )

        print(
            f"  Date Accuracy: "
            f"{result['experiences']['date_accuracy']:.2%}"
        )

        print(
            f"  Skills F1: "
            f"{result['skills']['f1']:.2%}"
        )

        print(
            f"  Experience Evidence F1: "
            f"{result['evidence']['experience']['f1']:.2%}"
        )

        print(
            f"  Summary: "
            f"{result['evidence']['summary']['score']:.2%}"
        )

        print(
            f"  Projects F1: "
            f"{result['evidence']['projects']['f1']:.2%}"
        )

        print(
            f"  Achievements F1: "
            f"{result['evidence']['achievements']['f1']:.2%}"
        )

        print(
            f"  Education F1: "
            f"{result['evidence']['education']['f1']:.2%}"
        )

        print(
            f"  Total Experience: "
            f"{result['total_experience']['predicted']} "
            f"/ "
            f"{result['total_experience']['actual']} "
            f"months"
        )

        print(
            f"  Overall Score: "
            f"{result['overall_score']:.2%}"
        )

        print()

    if results:
        average_score = (
            sum(
                result["overall_score"]
                for result in results
            )
            / len(results)
        )
    else:
        average_score = 0.0

    output = {
        "summary": {
            "resumes_evaluated": len(
                results
            ),
            "resumes_skipped": (
                len(ground_truth)
                - len(results)
            ),
            "average_score": round(
                average_score,
                4,
            ),
            "weights": {
                "experience_f1": 0.20,
                "date_accuracy": 0.10,
                "skills_f1": 0.20,
                "total_experience": 0.10,
                "experience_evidence_f1": 0.15,
                "projects_f1": 0.10,
                "education_f1": 0.05,
                "summary": 0.05,
                "achievements_f1": 0.03,
                "name": 0.01,
                "email": 0.005,
                "phone": 0.005,
            },
        },
        "results": results,
    }

    with open(
        RESULT_PATH,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            default=str,
        )

    print("=" * 80)
    print("FINAL RESULT")
    print("=" * 80)

    print(
        f"Resumes evaluated: "
        f"{len(results)}"
    )

    print(
        f"Resumes skipped: "
        f"{len(ground_truth) - len(results)}"
    )

    print(
        f"Average score: "
        f"{average_score:.2%}"
    )

    print(
        f"Saved to: {RESULT_PATH}"
    )


if __name__ == "__main__":
    main()