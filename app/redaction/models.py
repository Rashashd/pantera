"""Result types for in-process PII/secret redaction (category + count only, never values)."""

from pydantic import BaseModel


class RedactedEntity(BaseModel):
    """One redacted category and how many instances were replaced — never the original value."""

    # e.g. PERSON, DATE_TIME, PHONE_NUMBER, EMAIL_ADDRESS, LOCATION, MEDICAL_RECORD, SECRET
    type: str
    count: int


class RedactionResult(BaseModel):
    """Redacted text plus category counts; the original text/values are never retained."""

    text: str  # redacted string with placeholders like "<PERSON>", "<SECRET>"
    entities: list[RedactedEntity] = []
