"""Language-agnostic complexity estimate.

A proper per-language parser is overkill here; what correlates with bug risk is
the number of *decision points* in a file (McCabe's cyclomatic complexity is
essentially ``1 + decisions``). We approximate it by counting branch keywords
and boolean operators that exist across almost every language.

It is a proxy, not a compiler: it may miscount tokens inside strings or
comments. That's fine — it's applied consistently to every file, so the
*ranking* it produces is what matters, and it beats raw line count handily.
"""

from __future__ import annotations

import re

# Branch keywords shared across C/Java/JS/Python/Rust/Go/Ruby/... plus the
# boolean operators that add a path. Deliberately excludes the lone "?" (Rust's
# error-propagation operator would wildly inflate the count) and "=>" (arrow
# functions in JS are not branches).
_DECISION = re.compile(
    r"\b(if|elif|else\s+if|for|foreach|while|case|when|match|switch|catch|rescue|except)\b"
    r"|&&|\|\|",
)


def measure(data: bytes) -> tuple[int, int]:
    """Return (lines, complexity) for a file's raw bytes.

    Binary files get complexity == lines (a neutral value) so they never look
    artificially hot or cold.
    """
    if not data:
        return 0, 1
    lines = data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
    if b"\x00" in data[:4096]:  # looks binary — has no meaningful complexity
        return lines, 1
    text = data.decode("utf-8", "ignore")
    return lines, 1 + len(_DECISION.findall(text))
