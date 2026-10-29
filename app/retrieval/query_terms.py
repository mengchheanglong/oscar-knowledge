"""Bounded lexical alternatives; original questions remain the semantic input."""

import re

SEARCH_META = {
    "cite",
    "cited",
    "citation",
    "citations",
    "source",
    "sources",
    "sourced",
    "passage",
    "passages",
    "synthesize",
    "synthesise",
    "synthesis",
    "permitted",
    "library",
    "please",
    "explain",
    "answer",
    "question",
    "paragraph",
    "words",
}


def lexical_alternatives(query, stop_words):
    terms = list(
        dict.fromkeys(
            word.casefold()
            for word in re.findall(r"[^\W_]{2,}", query)
            if word.casefold() not in stop_words | SEARCH_META
        )
    )[:16]
    if not terms:
        return []
    # Adjacent content pairs retain concepts such as contribution margin while
    # avoiding a union of every common word across hundreds of thousands of pages.
    pairs = [f"{a} {b}" for a, b in zip(terms, terms[1:])]
    alternatives = [" OR ".join(pairs)] if pairs else []
    alternatives.append(" OR ".join(terms))
    return list(dict.fromkeys(alternatives))
