"""
Run with: python -m app.evals.run_evals
(from the backend/ directory, with OPENAI_API_KEY set)

Prints pass/fail for each case. This is meant to be run once after any
prompt change, and periodically as a regression check - not a CI gate by
itself unless you wire it into one.
"""
import sys
from app.evals.eval_cases import EVAL_CASES
from app.extraction.jd_extractor import extract_jd
from app.scoring.ai_content_detector import detect_ai_content_risk


def run():
    results = []

    # 1. JD schema conformance
    try:
        jd = extract_jd(EVAL_CASES["jd_extraction_schema"]["input"])
        ok = bool(jd.must_have_skills) and jd.role_title
        results.append(("jd_extraction_schema", ok, f"role={jd.role_title!r} must_have={jd.must_have_skills}"))
    except Exception as e:
        results.append(("jd_extraction_schema", False, f"EXCEPTION: {e}"))

    # 2. AI content detector - deterministic, no API key needed
    for key in ["ai_detector_should_flag_high", "ai_detector_should_flag_resume_cliches", "ai_detector_should_flag_low"]:
        case = EVAL_CASES[key]
        out = detect_ai_content_risk(case["input"])
        ok = out["risk_level"] == case["expect_risk_level"]
        results.append((key, ok, f"got={out['risk_level']} expected={case['expect_risk_level']}"))

    print("\n=== EVAL RESULTS ===")
    all_pass = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"[{status}] {name} - {detail}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    run()
