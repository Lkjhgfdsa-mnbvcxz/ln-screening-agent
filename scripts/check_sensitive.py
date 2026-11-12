"""Publication gate: scan every tracked text file for real business markers.

The public repository must contain SYNTHETIC data only.  This gate detects by
SHAPE, so it never stores a real case id, host, name or identifier itself.  A
stricter local pass can be added with ``--vocab <path>`` pointing at a file
that lives OUTSIDE the repository (e.g. the authorized local capture folder);
that vocabulary is never committed.

    python3 scripts/check_sensitive.py
    python3 scripts/check_sensitive.py --vocab /tmp/ln_sensitive_vocab.json

Exit code 0 = clean, 1 = findings, 2 = gate could not run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {".py", ".md", ".json", ".html", ".js", ".css", ".yaml",
                 ".yml", ".toml", ".txt", ".cfg", ".ini", ".sh", ".csv", ""}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".db",
                   ".sqlite", ".sqlite3", ".zip", ".gz", ".woff", ".woff2"}

# Patterns are assembled from fragments so this file never contains a literal
# real-looking identifier that could itself trip a naive scanner.
PATTERNS: dict[str, str] = {
    "real LN case id": r"LN" + r"20\d{9,}",
    "internal host": (r"(?:boss|fmc|gw|merchant)\.[a-z0-9-]+\.(?:com|cn)"
                      r"|[a-z0-9-]+\.(?:yee" + r"pay|fei" + r"shu)\.(?:com|cn)"
                      r"|boss" + r"-gpt"),
    "provider secret": r"sk-(?:proj|ant|live|test)-[A-Za-z0-9_-]{16,}",
    "platform token": r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
    "CN identity number": r"(?<!\d)\d{17}[\dXx](?!\d)",
    "unified social credit code": r"(?<!\d)91[0-9A-Z]{16}(?!\d)",
    "internal review route": (r"(?:GPT" + r"CheckListManage|Screen" +
                              r"CheckDetail|check" + r"List=|merchant" + r"No=)"),
    "authorized-capture marker": (r"YEE" + r"PAY_|AUTHORIZED LOCAL " +
                                  r"REAL DATA"),
}
COMPILED = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}


def find_in_text(text: str, vocab: list[str] | None = None) -> list[tuple[str, str]]:
    """Return (reason, matched-fragment) findings for one text blob."""
    found: list[tuple[str, str]] = []
    for label, pattern in COMPILED.items():
        for match in pattern.finditer(text):
            found.append((label, match.group(0)[:80]))
    for term in vocab or []:
        if term and term in text:
            found.append(("local sensitive vocabulary", term[:80]))
    return found


def tracked_files() -> list[Path]:
    """Tracked files plus new, not-yet-added files (ignored paths excluded)."""
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    pending = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True)
    lines = tracked.splitlines() + pending.splitlines()
    return [ROOT / line for line in lines if line.strip()]


def scan(vocab: list[str] | None = None) -> dict[str, list[tuple[str, str]]]:
    findings: dict[str, list[tuple[str, str]]] = {}
    for path in tracked_files():
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = find_in_text(text, vocab)
        if hits:
            findings[str(path.relative_to(ROOT))] = hits
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", type=Path, default=None,
                    help="optional OUT-OF-REPO JSON list of sensitive terms")
    args = ap.parse_args()
    vocab = None
    if args.vocab:
        if args.vocab.resolve().is_relative_to(ROOT.resolve()):
            print("refusing to read a vocabulary stored inside the public repo", file=sys.stderr)
            return 2
        vocab = json.loads(args.vocab.read_text(encoding="utf-8"))
    try:
        findings = scan(vocab)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"gate could not run: {exc}", file=sys.stderr)
        return 2
    if not findings:
        print(f"publication gate: clean ({len(tracked_files())} tracked files, "
              f"{len(PATTERNS)} shape rules, vocab={'yes' if vocab else 'no'})")
        return 0
    for path, hits in sorted(findings.items()):
        for reason, fragment in hits[:12]:
            print(f"BLOCKED {path}: {reason} -> {fragment!r}", file=sys.stderr)
    print(f"publication gate: {sum(len(v) for v in findings.values())} finding(s)",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
