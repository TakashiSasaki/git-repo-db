"""Check active validation instructions for ADR 0032 regressions, using stdlib only.

This is a bounded configuration lint, not a proof about arbitrary programs or
natural language. Product guards and frozen evidence are outside its scope.
Extend LIVE_DOCS when adding a new validation entry point. No source exemptions
or inline suppression directives are accepted; approved exceptions need a scoped
policy/checker change with the owner's approval.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = "scripts/check_sqlite_validation_policy.py"
LIVE_DOCS = frozenset(
    {
        "README.md",
        "docs/testing.md",
        "docs/change-aware-ci.md",
        "docs/ci-performance.md",
        "docs/test-suite-efficiency.md",
        "docs/site/development/index.md",
        "docs/architecture/git-core-context-transition-plan.md",
        "docs/implementation/context-resource-design-handoff.md",
        "docs/implementation/context-exchange-design-handoff.md",
        "docs/implementation/p1-schema-contracts.md",
        "docs/implementation/adr0031-i2-implementation-preparation.md",
        "docs/implementation/adr0031-i2-implementation.md",
        "docs/adr/0032-environment-sqlite-validation.md",
    }
)
SOURCE_SUFFIXES = {".py", ".sh", ".bash", ".yml", ".yaml", ".json", ".md", ".toml"}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str


def in_scope(path: str) -> bool:
    parts = Path(path).parts
    if path == SELF or "evidence" in parts or "fixtures" in parts:
        return False
    if path in LIVE_DOCS or Path(path).name == "AGENTS.md":
        return True
    return (
        path.startswith(
            ("scripts/", ".agents/", ".github/workflows/", ".github/actions/")
        )
        or path.startswith(".github/")
        and path.endswith(".md")
    ) and Path(path).suffix in SOURCE_SUFFIXES


RULES = {
    "sqlite-download": r"https?://(?:www\.)?sqlite\.org/[^\s\"']*sqlite-(?:amalgamation|autoconf|tools)",
    "sqlite-compile": r"\b(?:cc|gcc|clang|make|cmake)\b[^\n]*(?:sqlite3\.c|SQLITE_C|libsqlite3)",
    "sqlite-install": r"\b(?:pip3?|uv\s+pip|apt(?:-get)?|brew)\b[^\n]*\binstall\b[^\n]*(?:pysqlite3|libsqlite3|\bsqlite3?\b)",
    "sqlite-library-swap": r"(?:\b(?:LD_LIBRARY_PATH|LD_PRELOAD|DYLD_LIBRARY_PATH)\s*=|[\"'](?:LD_LIBRARY_PATH|LD_PRELOAD|DYLD_LIBRARY_PATH)[\"']\s*\]\s*=|[\"'](?:LD_LIBRARY_PATH|LD_PRELOAD|DYLD_LIBRARY_PATH)[\"']\s*:(?!\s*(?:os\.)?(?:environ\.get|getenv)\b)\s*)",
    "sqlite-matrix": r"(?:matrix\s*\.\s*sqlite[\w-]*|\bsqlite[\w-]*\s*:\s*\[[^\]\n]*,[^\]\n]*\]|\bsqlite[\w-]*\s*:\s*\n(?:[ \t]+-[^\n]+\n){2,})",
    "sqlite-version-option": r"--(?:sqlite(?:-version|-source-id)?|minimum-library|newer-library)(?![\w-])",
    "sqlite-exact-gate": r"(?:assert|if|test)\b[^\n]*(?:sqlite_version(?:_info)?|sqlite_source_id\s*\([^\n]*?\))[^\n]*(?:==|!=|\s=\s)[^\n]*(?:[\"']\d+\.\d+\.\d+[\"']|\(\s*3\s*,\s*\d+\s*,\s*\d+\s*\))",
}
COMPILED = {name: re.compile(pattern, re.I) for name, pattern in RULES.items()}
NEGATIVE = re.compile(
    r"\b(?:do not|must not|never|no longer|prohibit\w*|removed?|retired?)\b|\bwithout\s+(?:(?:a|the|any)\s+)?$",
    re.I,
)
JAPANESE_NEGATIVE = re.compile(
    r"禁止|不要|廃止|撤廃|要求しません|しない|しません|必要はな"
)
HISTORICAL = re.compile(
    r"\b(?:historical|previous(?:ly)?|completed|observed|used to|was measured)\b|過去|以前|実行済",
    re.I,
)
INSTRUCTION = re.compile(
    r"\b(?:run|test|verify|validate|require|must|build|compile|download|install|use|set)\b|実行|検証|必須|構築|導入|ビルド",
    re.I,
)
PROSE_BAD = re.compile(
    r"(?:\b(?:download|build|compile|install|swap|replace)\s+(?:(?:the|a|test|specific|fixed|pinned)\s+)*sqlite\b"
    r"|\bsqlite\s+(?:version\s+)?(?:matrix|source\s+build)\b"
    r"|\b(?:minimum|oldest)\b.{0,100}\b(?:newer|newest|latest)\b.{0,100}\bsqlite\b"
    r"|\b(?:minimum|oldest)\b.{0,60}\bsqlite\b.{0,100}\b(?:newer|newest|latest)\b"
    r"|\bsqlite\b.{0,100}\b(?:minimum|oldest)\b.{0,100}\b(?:newer|newest|latest)\b"
    r"|\b(?:both|multiple|two)\b.{0,40}\bsqlite\s+(?:versions|releases|runtimes|libraries|bindings)\b"
    r"|\b(?:both|multiple|two)\s+(?:versions|releases|runtimes|libraries|bindings)\s+of\s+sqlite\b"
    r"|\bsqlite\b.{0,40}\b(?:both|multiple|two|exact)\s+(?:versions|releases|runtimes|libraries|bindings|source IDs)\b"
    r"|\b(?:exact|fixed|pinned)\s+sqlite\s+(?:version|source ID|runtime|release)\b"
    r"|\bsqlite\b.{0,30}3\.\d+\.\d+.{0,30}3\.\d+\.\d+"
    r"|\bsqlite\s+3\.\d+\.\d+\s+(?:interpreter|binding|runtime)\b"
    r"|SQLite.{0,60}(?:二版|複数版|最低版と新版|ソースビルド))",
    re.I,
)


def python_rules(text: str) -> set[tuple[int, str]]:
    """Recognize fixed SQLite equality gates, including query/constant aliases."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()  # Shell/YAML snippets are covered by lexical rules.
    nodes = list(ast.walk(tree))
    aliases = {"sqlite3"}
    for node in nodes:
        if isinstance(node, ast.Import):
            aliases.update(
                n.asname or n.name for n in node.names if n.name == "sqlite3"
            )
    measured = set()
    constants = set()
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and node.module == "sqlite3":
            measured.update(
                n.asname or n.name
                for n in node.names
                if n.name in {"sqlite_version", "sqlite_version_info"}
            )
    assignments = [n for n in nodes if isinstance(n, (ast.Assign, ast.AnnAssign))]

    def is_measured(node):
        if isinstance(node, (ast.Dict, ast.List)):
            return False  # A report containing identity fields is not itself a version.
        return any(
            isinstance(n, ast.Name)
            and n.id in measured
            or isinstance(n, ast.Attribute)
            and n.attr in {"sqlite_version", "sqlite_version_info"}
            and isinstance(n.value, ast.Name)
            and n.value.id in aliases
            or isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and re.search(r"\bsqlite_(?:version|source_id)\s*\(", n.value, re.I)
            for n in ast.walk(node)
        )

    def fixed(node):
        if isinstance(node, ast.Name):
            return node.id in constants
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if (
                isinstance(node.value.value, ast.Name)
                and node.value.value.id == "sys"
                and node.value.attr == "argv"
            ):
                return True
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "args" and "sqlite" in node.attr:
                return True
        try:
            value = ast.literal_eval(node)
        except (ValueError, TypeError):
            return False
        return isinstance(value, (str, tuple, list))

    for _ in range(len(assignments) + 1):
        before = (len(measured), len(constants))
        for node in assignments:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {target.id for target in targets if isinstance(target, ast.Name)}
            if node.value and is_measured(node.value):
                measured.update(names)
            if node.value and fixed(node.value):
                constants.update(names)
        if before == (len(measured), len(constants)):
            break
    findings = set()
    for node in nodes:
        if isinstance(node, ast.Compare):
            left = node.left
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and (
                    is_measured(left)
                    and fixed(right)
                    or fixed(left)
                    and is_measured(right)
                ):
                    findings.add((node.lineno, "sqlite-exact-gate"))
                left = right
        # Generated Python probes can contain a version gate inside a string.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.search(
                r"\b(?:import\s+[^\n;]*\bsqlite3\b|from\s+sqlite3\s+import\b)",
                node.value,
            )
        ):
            findings.update(
                (node.lineno + line - 1, rule)
                for line, rule in python_rules(node.value)
            )
        if isinstance(node, ast.For) and "sqlite" in text.lower():
            versions = {
                n.value
                for n in ast.walk(node.iter)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and re.fullmatch(r"3\.\d+\.\d+", n.value)
            }
            if len(versions) > 1:
                findings.add((node.lineno, "sqlite-matrix"))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"run", "check_call", "check_output"}
        ):
            # Also inspect literal subprocess argv, not only shell command text.
            for arg in node.args:
                if isinstance(arg, (ast.List, ast.Tuple)) and all(
                    isinstance(n, ast.Constant) and isinstance(n.value, str)
                    for n in arg.elts
                ):
                    command = " ".join(n.value for n in arg.elts)
                    for rule in ("sqlite-download", "sqlite-compile", "sqlite-install"):
                        if COMPILED[rule].search(command):
                            findings.add((node.lineno, rule))
    return findings


def code_rules(text: str) -> set[tuple[int, str]]:
    findings = python_rules(text)
    # Parse Python heredocs inside shell/YAML without requiring a YAML package.
    lines = text.splitlines()
    for index, line in enumerate(lines):
        start = re.search(r"\bpython[\w.-]*\s+-\s+<<\s*['\"]?(\w+)", line)
        if start:
            end = next(
                (
                    n
                    for n in range(index + 1, len(lines))
                    if lines[n].strip() == start[1]
                ),
                len(lines),
            )
            body = textwrap.dedent("\n".join(lines[index + 1 : end]))
            findings.update((index + n + 1, rule) for n, rule in python_rules(body))
    # Equal-length substitutions preserve original offsets across continuations.
    joined = re.sub(r"\\\n[ \t]*", lambda m: " " * len(m[0]), text)
    for rule, pattern in COMPILED.items():
        for match in pattern.finditer(joined):
            # The option name itself is forbidden in active executable commands:
            # it selects a test SQLite rather than recording measured identity.
            findings.add((text.count("\n", 0, match.start()) + 1, rule))
    return findings


def inspect(path: str, text: str) -> list[Finding]:
    if not in_scope(path):
        return []
    found = set()
    if not path.endswith(".md"):
        found.update(code_rules(text))
    else:
        fenced = False
        block = []
        block_start = 0
        paragraph = []

        def prose():
            value = " ".join(line.strip() for _, line in paragraph)
            # Keep negation with its instruction. A later "without disabling
            # safety" / "never spoof" clause cannot excuse a version matrix.
            clauses = re.split(
                r"(?<=。)|(?<=[.!?;])\s+|\b(?:and|but)\s+(?=(?:do not|never|run|require|build|download|install)\b)",
                value,
                flags=re.I,
            )
            for clause in clauses:
                for violation in PROSE_BAD.finditer(clause):
                    prefix = clause[: violation.start()]
                    if (
                        not NEGATIVE.search(prefix)
                        and not HISTORICAL.search(prefix)
                        and not JAPANESE_NEGATIVE.search(clause)
                        and INSTRUCTION.search(clause)
                    ):
                        found.add((paragraph[0][0], "sqlite-procedure"))
            paragraph.clear()

        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                prose()
                if fenced:
                    found.update(
                        (block_start + n - 1, rule)
                        for n, rule in code_rules("\n".join(block))
                    )
                    block.clear()
                fenced = not fenced
                block_start = lineno + 1
            elif fenced:
                block.append(line)
            elif line.startswith("|"):
                prose()
                paragraph.append((lineno, line))
                prose()
            elif line.strip():
                paragraph.append((lineno, line))
            else:
                prose()
        prose()
        if fenced:
            found.update(
                (block_start + n - 1, rule) for n, rule in code_rules("\n".join(block))
            )
    return [Finding(path, line, rule) for line, rule in sorted(found)]


def scan(root: Path, paths: list[str]) -> list[Finding]:
    return sorted(
        finding
        for path in sorted(set(paths))
        if in_scope(path) and (root / path).is_file()
        for finding in inspect(path, (root / path).read_text(encoding="utf-8"))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    paths = (
        subprocess.check_output(["git", "-C", str(args.root), "ls-files", "-z"])
        .decode()
        .split("\0")
    )
    findings = scan(args.root, paths)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule} (ADR 0032)")
    print(f"SQLite validation policy: {len(findings)} violation(s)")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
