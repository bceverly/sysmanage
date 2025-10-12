"""
Common utilities for HTML report generation
"""

import html


def escape(value) -> str:
    """Escape HTML characters to prevent XSS attacks"""
    if value is None:
        return ""
    return html.escape(str(value))
