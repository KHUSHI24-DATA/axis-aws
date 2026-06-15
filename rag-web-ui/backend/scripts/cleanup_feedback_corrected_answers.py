"""Safely clean bad corrected answers from thumbs-down feedback.

By default this script runs in dry-run mode and reports what would change.
Use --apply to persist updates.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

# Allow running the script directly via:
#   python scripts/cleanup_feedback_corrected_answers.py
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.chat import Message

GENERIC_BAD_ANSWERS = {
    "incorrect",
    "wrong",
    "not correct",
    "bad answer",
    "n/a",
    "na",
    "none",
    "idk",
}


def normalize_text(value: str | None) -> str:
    """Normalize free text for conservative matching."""
    if not value:
        return ""
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return lowered.strip()


def should_clear_corrected_answer(message: Message) -> bool:
    """Return True only for clearly bad corrected answers."""
    if message.feedback_type != "down":
        return False

    corrected = normalize_text(message.corrected_answer)
    if not corrected:
        return False

    note = normalize_text(message.feedback_note)
    if note and corrected == note:
        return True

    return corrected in GENERIC_BAD_ANSWERS


def get_candidates(db: Session) -> list[Message]:
    """Load potential rows conservatively for cleanup."""
    return (
        db.query(Message)
        .filter(
            Message.role == "assistant",
            Message.feedback_type == "down",
            Message.corrected_answer.isnot(None),
        )
        .all()
    )


def cleanup_feedback_answers(apply_changes: bool, limit: int | None = None) -> int:
    """Cleanup operation with rollback-safe behavior."""
    db = SessionLocal()
    updated_count = 0
    try:
        candidates = get_candidates(db)
        to_update: list[Message] = [m for m in candidates if should_clear_corrected_answer(m)]
        if limit is not None:
            to_update = to_update[:limit]

        print(f"Scanned {len(candidates)} down-feedback messages with corrected_answer.")
        print(f"Matched {len(to_update)} rows to clean.")

        for message in to_update:
            print(
                f"- message_id={message.id} chat_id={message.chat_id} "
                f"corrected_answer={message.corrected_answer!r} feedback_note={message.feedback_note!r}"
            )
            if apply_changes:
                message.corrected_answer = None
                updated_count += 1

        if apply_changes:
            db.commit()
            print(f"Applied cleanup successfully. Updated {updated_count} rows.")
        else:
            db.rollback()
            print("Dry run only. No changes written.")

        return updated_count
    except Exception as exc:
        db.rollback()
        print(f"Cleanup failed. Transaction rolled back. Error: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    """Parse command-line flags."""
    parser = argparse.ArgumentParser(
        description="Clean bad corrected_answer values from thumbs-down feedback."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag the script runs as dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of matched rows to update/report.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    cleanup_feedback_answers(apply_changes=args.apply, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
