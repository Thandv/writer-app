"""
Reviser — thin wrapper around Drafter that re-drafts with critique attached.
"""

from .shared.memory import BookProject
from . import drafter


def revise(project: BookProject, book_n: int, chapter_n: int,
           chapter_title: str, beat_body: str,
           previous_chapter_text: str,
           revision_note: str) -> str:
    return drafter.run(
        project, book_n, chapter_n, chapter_title, beat_body,
        previous_chapter_text=previous_chapter_text,
        revision_note=revision_note,
    )
