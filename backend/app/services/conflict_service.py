"""
ComplyFlow — Fact-Level Conflict Detection & Grounding Service

Provides auditable, fact-level conflict analysis between competing document sources.
Eliminates false-positive conflicts caused by harmless formatting/normalization differences.
Guarantees that both competing values are grounded in actual source text excerpts.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from app.agent.schemas import ConflictDetail, ConflictingSource, EvidenceCitation, Priority
from app.services.citation_validator import normalize_for_matching


class ConflictService:
    """Detects, normalizes, and grounds fact-level conflicts across evidence sources."""

    # Common entity suffix equivalences
    LEGAL_SUFFIX_MAP = {
        r"\bincorporated\b": "inc",
        r"\bcorporation\b": "corp",
        r"\blimited liability company\b": "llc",
        r"\blimited\b": "ltd",
        r"\bcompany\b": "co",
    }

    # Address word equivalences
    ADDRESS_MAP = {
        r"\bstreet\b": "st",
        r"\bavenue\b": "ave",
        r"\bboulevard\b": "blvd",
        r"\bdrive\b": "dr",
        r"\broad\b": "rd",
        r"\bsuite\b": "ste",
        r"\bfloor\b": "fl",
        r"\bbuilding\b": "bldg",
    }

    def normalize_value(self, val: str) -> str:
        """Normalize a fact value for semantic comparison (address, name, date, amount)."""
        if not val:
            return ""
        norm = normalize_for_matching(val)
        
        # Remove punctuation
        norm = re.sub(r"[.,\-#/]", " ", norm)
        
        # Normalize legal suffixes
        for pat, rep in self.LEGAL_SUFFIX_MAP.items():
            norm = re.sub(pat, rep, norm)
            
        # Normalize address abbreviations
        for pat, rep in self.ADDRESS_MAP.items():
            norm = re.sub(pat, rep, norm)

        # Standardize whitespace
        norm = re.sub(r"\s+", " ", norm).strip()
        return norm

    def are_values_equivalent(self, val_a: str, val_b: str) -> bool:
        """
        Check whether two values represent the same factual entity without contradiction.
        Avoids false-positive conflicts.
        """
        if not val_a or not val_b:
            return True

        norm_a = self.normalize_value(val_a)
        norm_b = self.normalize_value(val_b)

        # 1. Exact normalized match
        if norm_a == norm_b:
            return True

        # 2. Date format equivalency check (e.g. 2026-01-01 vs January 1 2026)
        date_a = self._extract_date_components(norm_a)
        date_b = self._extract_date_components(norm_b)
        if date_a and date_b and date_a == date_b:
            return True

        # 3. Currency / Number formatting equivalency (e.g. $2,000,000 vs 2000000 USD vs $2M)
        num_a = self._extract_monetary_value(norm_a)
        num_b = self._extract_monetary_value(norm_b)
        if num_a is not None and num_b is not None and num_a == num_b:
            return True

        return False

    def verify_value_in_citation(self, value: str, citation: EvidenceCitation) -> bool:
        """Check if an extracted conflicting fact value is grounded in the citation quote."""
        if not value or not citation or not citation.quote:
            return False
        
        norm_val = normalize_for_matching(value)
        norm_quote = normalize_for_matching(citation.quote)
        
        if norm_val in norm_quote:
            return True

        # Check keywords/tokens (e.g., "Suite 800" in "Suite 800, Innovation Park")
        tokens = [t for t in norm_val.split() if len(t) > 2]
        if tokens and all(t in norm_quote for t in tokens):
            return True

        return False

    def build_fact_conflict(
        self,
        requirement_id: str,
        fact: str,
        fact_label: str,
        citation_a: EvidenceCitation,
        value_a: str,
        citation_b: EvidenceCitation,
        value_b: str,
        explanation: str,
        severity: Priority = Priority.HIGH,
        recommended_action: str = "",
    ) -> Optional[ConflictDetail]:
        """
        Construct a grounded ConflictDetail.
        Rejects false-positives and ungrounded conflicting values.
        """
        # 1. False positive check
        if self.are_values_equivalent(value_a, value_b):
            return None

        # 2. Grounding check
        grounded_a = self.verify_value_in_citation(value_a, citation_a)
        grounded_b = self.verify_value_in_citation(value_b, citation_b)

        if not grounded_a or not grounded_b:
            # Reject if either competing value cannot be found in the respective source quote
            return None

        if not recommended_action:
            recommended_action = (
                f"Verify the authoritative {fact_label.lower()} between {citation_a.document_name} "
                f"and {citation_b.document_name}, and upload an updated/reconciled document."
            )

        return ConflictDetail(
            related_requirement_id=requirement_id,
            fact=fact,
            fact_label=fact_label,
            source_a=ConflictingSource(citation=citation_a, value=value_a),
            source_b=ConflictingSource(citation=citation_b, value=value_b),
            explanation=explanation,
            severity=severity,
            recommended_action=recommended_action,
        )

    # ── Private helper parsers ───────────────────────────────────

    def _extract_date_components(self, text: str) -> Optional[Tuple[int, int, int]]:
        months = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
            "november": 11, "nov": 11, "december": 12, "dec": 12
        }
        # Match YYYY-MM-DD
        iso_match = re.search(r"\b(20\d\d)[-\s](0?[1-9]|1[0-2])[-\s](0?[1-9]|[12]\d|3[01])\b", text)
        if iso_match:
            return (int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))

        # Match Month DD, YYYY
        for m_name, m_num in months.items():
            pattern = rf"\b{m_name}\s+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+(20\d\d)\b"
            m = re.search(pattern, text)
            if m:
                return (int(m.group(2)), m_num, int(m.group(1)))

        return None

    def _extract_monetary_value(self, text: str) -> Optional[float]:
        # Match $2,000,000 or 2M or 2 million
        m_millions = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|million)", text)
        if m_millions:
            return float(m_millions.group(1)) * 1_000_000

        m_num = re.search(r"\$?\s*(\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?)", text)
        if m_num:
            clean = m_num.group(1).replace(",", "").replace(" ", "")
            try:
                return float(clean)
            except ValueError:
                pass
        return None


# Global singleton
_conflict_service_instance: Optional[ConflictService] = None


def get_conflict_service() -> ConflictService:
    global _conflict_service_instance
    if _conflict_service_instance is None:
        _conflict_service_instance = ConflictService()
    return _conflict_service_instance
