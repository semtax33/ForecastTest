from .html import HtmlFragment, adapt_html_document, adapt_html_fragments
from .model import (
    CanonicalDocument,
    DocumentMetadata,
    DocumentSentence,
    DocumentTable,
    InlineFact,
)

__all__ = [
    "adapt_html_document",
    "adapt_html_fragments",
    "HtmlFragment",
    "CanonicalDocument",
    "DocumentMetadata",
    "DocumentSentence",
    "DocumentTable",
    "InlineFact",
]
