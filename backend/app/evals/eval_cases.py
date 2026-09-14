"""
Hand-authored eval cases. This is a lightweight, dependency-free local
eval harness - not an integration with a named third-party eval platform.
If you want heavier tooling later, look at promptfoo, DeepEval, or
OpenAI's own Evals product, but VERIFY their current setup/APIs yourself
before adopting one - eval tooling in this space moves fast and I can't
confirm which of these best matches your needs as of today.

Each case checks one thing in isolation:
- schema conformance (does extraction return a valid, complete object)
- evidence-strength judgment on a clear-cut synthetic example (a skill
  that is ONLY listed vs. a skill that is defended with a concrete bullet)
- AI-content-detector precision on an obviously formulaic paragraph vs an
  obviously plain, specific one
"""

JD_SAMPLE = """
We are hiring a Backend Engineer (Mid-level).
Must have: Python, PostgreSQL, REST API design, Docker.
Nice to have: Kubernetes, AWS.
Responsibilities: build and maintain backend services, design APIs, own database schema decisions.
Minimum 3 years of experience required.
Bachelor's degree in Computer Science or related field.
"""

RESUME_SKILL_ONLY = """
Skills: Python, PostgreSQL, Docker, Kubernetes, REST API design

Experience:
Software Engineer, Acme Corp, 2021-2024
- Worked on various backend tasks and features
- Collaborated with the team on multiple projects
"""

RESUME_SKILL_DEFENDED = """
Skills: Python, PostgreSQL, Docker, REST API design

Experience:
Software Engineer, Acme Corp, 2021-2024
- Designed and shipped a REST API in Python/Flask handling 40k requests/day, backed by a PostgreSQL schema I redesigned to cut query latency 35%
- Containerized the service with Docker and wrote the CI pipeline that builds and pushes images on every merge
"""

AI_FORMULAIC_PARAGRAPH = """
In today's fast-paced world, it is important to note that I am a results-driven professional.
I leverage cutting-edge, state-of-the-art solutions to seamlessly integrate robust and scalable
systems, ensuring success and driving impact. It's not just about writing code, it's about
delivering value.
"""

# Regression case for the "resume clichés weren't in the pattern list" bug -
# uses realistic AI-resume phrasing that intentionally avoids overlap with
# AI_FORMULAIC_PARAGRAPH's phrases above.
AI_RESUME_CLICHE_PARAGRAPH = """
I am a results-driven professional with a proven track record of success. I have extensive
experience and excellent communication skills. As a detail-oriented team player, I am passionate
about delivering high-quality work and driving impactful outcomes. Furthermore, I have a strong
ability to navigate complex challenges and foster collaboration across cross-functional teams.
"""

PLAIN_SPECIFIC_PARAGRAPH = """
I rewrote our checkout service's payment retry logic after we lost about $12k in one week to
duplicate charges. Root cause was a race condition between two workers. Fixed it with a
Postgres advisory lock and added an idempotency key to the payments table.
"""

EVAL_CASES = {
    "jd_extraction_schema": {"input": JD_SAMPLE},
    "skill_defense_should_flag": {"input": RESUME_SKILL_ONLY, "expect_undefended": ["Kubernetes", "PostgreSQL"]},
    "skill_defense_should_pass": {"input": RESUME_SKILL_DEFENDED, "expect_undefended": []},
    "ai_detector_should_flag_high": {"input": AI_FORMULAIC_PARAGRAPH, "expect_risk_level": "high"},
    "ai_detector_should_flag_resume_cliches": {"input": AI_RESUME_CLICHE_PARAGRAPH, "expect_risk_level": "high"},
    "ai_detector_should_flag_low": {"input": PLAIN_SPECIFIC_PARAGRAPH, "expect_risk_level": "low"},
}
