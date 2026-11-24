#!/usr/bin/env python3
"""Scan the repo for anything that should not be published.

This runs before every commit. It flags contact data, identifiers, absolute
paths, vendor secrets, and the names of private automations. The author's own
name is allowed in README.md only.

Exit code 1 if anything outside the allowlist turns up.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
# The scanner defines the patterns, and the private term list is the term list,
# so neither can meaningfully be scanned by this script.
SKIP_FILES = {os.path.join(ROOT, "pii_scan.py"), os.path.join(ROOT, "private_terms.txt")}

PATTERNS = [
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    ("phone number", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")),
    ("absolute user path", re.compile(r"/Users/[A-Za-z0-9._-]+")),
    ("home path", re.compile(r"/home/[A-Za-z0-9._-]+")),
    ("chat/channel id", re.compile(r"\b[0-9a-f]{12,16}\b")),
    ("api key shape", re.compile(r"\b(?:sk|pk|ghp|xox[bp])[-_][A-Za-z0-9]{16,}")),
    ("ipv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("messenger platform", re.compile(r"(?i)\bnitter\b|\bwhatsapp\b|\bimessage\b|\btelegram\b")),
]

# Personal terms (names of private automations, drives, vault tools) live in a
# gitignored file so the published scanner carries no personal vocabulary.
_PRIVATE = os.path.join(ROOT, "private_terms.txt")
if os.path.exists(_PRIVATE):
    for _term in (l.strip() for l in open(_PRIVATE, encoding="utf-8")):
        if _term and not _term.startswith("#"):
            PATTERNS.append(("private term", re.compile(re.escape(_term), re.IGNORECASE)))

ALLOW = {"README.md": [re.compile(r"Ryan J\. Sullivan"), re.compile(r"linkedin\.com/in/ryanjsullivan")]}


def main():
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            if path in SKIP_FILES:
                continue
            rel = os.path.relpath(path, ROOT)
            try:
                text = open(path, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            allowed = ALLOW.get(rel, [])
            for label, rx in PATTERNS:
                for m in rx.finditer(text):
                    if any(a.search(m.group(0)) for a in allowed):
                        continue
                    line = text[:m.start()].count("\n") + 1
                    hits.append((rel, line, label, m.group(0)[:60]))
    if hits:
        print(f"PII/secret scan: {len(hits)} finding(s)")
        for rel, line, label, val in hits:
            print(f"  {rel}:{line}  {label}  {val!r}")
        return 1
    print("PII/secret scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
