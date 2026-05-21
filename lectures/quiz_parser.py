"""Quiz markdown parser — ported from desktop main_window._parse_quiz_markdown."""
from __future__ import annotations

import re
from typing import Any


def parse_quiz_markdown(content: str) -> list[dict[str, Any]]:
    text = (content or "").strip()
    if not text:
        return []

    for _ in range(2):
        lines = text.splitlines()
        if (
            len(lines) >= 2
            and lines[0].strip().startswith("```")
            and lines[-1].strip() == "```"
        ):
            text = "\n".join(lines[1:-1]).strip()
        else:
            break

    answer_key_match = re.search(
        r"^\s*#{0,3}\s*Answer\s*Key\b.*$", text, flags=re.IGNORECASE | re.MULTILINE
    )
    if answer_key_match:
        questions_part = text[: answer_key_match.start()].strip()
        answers_part = text[answer_key_match.end() :].strip()
    else:
        alt = re.search(
            r"^\s*#{0,3}\s*Answers\b.*$", text, flags=re.IGNORECASE | re.MULTILINE
        )
        if alt:
            questions_part = text[: alt.start()].strip()
            answers_part = text[alt.end() :].strip()
        else:
            questions_part = text
            answers_part = ""

    answers: dict[int, dict[str, str | None]] = {}
    if answers_part:
        for line in answers_part.splitlines():
            raw = line.strip()
            if not raw:
                continue
            m = re.match(
                r"^\s*(?:Q\s*)?(\d{1,3})\s*[-\)\.:]*\s*([A-D])\b(?:\s*[-–—:]+\s*(.*))?$",
                raw,
                flags=re.IGNORECASE,
            )
            if not m:
                continue
            qn = int(m.group(1))
            letter = m.group(2).upper()
            expl = (m.group(3) or "").strip() or None
            answers[qn] = {"answer": letter, "explanation": expl}

    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    q_start = re.compile(r"^\s*(\d{1,3})\s*[\)\.:]\s+(.*)$")
    opt = re.compile(r"^\s*(?:[-*]\s*)?([A-D])\s*[\)\.:]\s+(.*)$", flags=re.IGNORECASE)

    def flush() -> None:
        nonlocal current
        if not current:
            return
        q_text = " ".join(
            [s.strip() for s in current.get("question_lines", []) if s.strip()]
        ).strip()
        current["question"] = q_text
        current.pop("question_lines", None)
        qn = int(current["number"])
        ans = answers.get(qn)
        if ans:
            current["answer"] = ans.get("answer")
            current["explanation"] = ans.get("explanation")
        else:
            current["answer"] = None
            current["explanation"] = None
        items.append(current)
        current = None

    for line in questions_part.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            if current and current.get("question_lines"):
                current["question_lines"].append("")
            continue
        m_q = q_start.match(raw)
        if m_q:
            flush()
            current = {
                "number": int(m_q.group(1)),
                "question_lines": [m_q.group(2).strip()],
                "options": {},
            }
            continue
        m_o = opt.match(raw)
        if m_o and current is not None:
            current["options"][m_o.group(1).upper()] = m_o.group(2).strip()
            continue
        if current is not None:
            current["question_lines"].append(raw.strip())
    flush()

    return [
        it
        for it in items
        if all(k in (it.get("options") or {}) for k in ("A", "B", "C", "D"))
    ]
