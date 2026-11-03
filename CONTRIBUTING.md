# Contributing

Small, focused improvements are welcome.

- Open an issue first for anything larger than a typo or a clearer example, so the scope can be agreed before work starts.
- Never weaken the safety rules: a link-check rule must be in the code and covered by a test, and no status is ever invented to fill a gap.
- Every claim in a proposed change must be verifiable: a command must be runnable, a feature must exist in code, a badge must be true.
- Run `python3 tests/test_broken_link_checker.py` before opening a pull request. It must pass.
- Do not add placeholder text, invented features, or copied content without attribution.
- Python standard library only — no new dependency without a reason in the issue.
