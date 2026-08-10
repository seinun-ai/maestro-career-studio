import re
from typing import Any, Literal


DocumentType = Literal["Resume", "CoverLetter"]


def _words(value: Any, fallback: str) -> list[str]:
    text = str(value or fallback)
    words = re.findall(r"[A-Za-z0-9]+", text)
    return words or [fallback]


def _compact(value: Any, fallback: str) -> str:
    return "".join(word[:1].upper() + word[1:] for word in _words(value, fallback))


def _name_parts(contact: dict[str, Any]) -> tuple[str, str]:
    words = _words(contact.get("name"), "Candidate")
    return words[-1], words[0]


def artifact_stem(
    *,
    contact: dict[str, Any],
    role: str | None,
    document_type: DocumentType,
) -> str:
    last_name, first_name = _name_parts(contact)
    # Date + company are already encoded in the folder name (Company_Role_YYYYMMDD),
    # so the file stem stays lean: FirstName_LastName_Role_DocumentType.
    return "_".join(
        [
            first_name,
            last_name,
            _compact(role, "Role"),
            document_type,
        ]
    )
