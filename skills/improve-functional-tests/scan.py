#!/usr/bin/env python3
"""Static signal collector for PHPUnit test suites.

Emits JSON on stdout. No judgment, only measurable facts — the agent decides.

Usage:
  python3 scan.py <target-dir-or-file> [--src DIR] [--timings FILE] [--db-base REGEX]

  --src DIR       production code root; emits the coverage map (`untested`):
                  classes whose name never appears in any test source under <target>'s
                  test root (auto-detected: nearest ancestor named tests/Test/Tests).
  --timings FILE  PHPUnit cache (`.phpunit.cache/test-run-history` or `test-results`,
                  format v2: {"version":2,"defects":{...},"times":{...}}). Joins real
                  seconds per test method and recent defects.
  --db-base REGEX extra regex for a project-specific DB/kernel base test class.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ASSERT_RE = re.compile(r"\$this\s*->\s*(assert\w+|expectException\w*|expectError\w*|assertThat)\s*\(")
SELF_ASSERT_RE = re.compile(r"\b(?:self|static)::(assert\w+|expectException\w*)\s*\(")
MOCK_EXPECT_RE = re.compile(r"->expects\s*\(|->shouldReceive\s*\(|->willThrow\w*\s*\(")
ANY_METHOD_RE = re.compile(
    r"(?:(#\[Test\][^\n]*\n\s*)|(?:/\*\*(?:(?!\*/).)*@test(?:(?!\*/).)*\*/\s*))?"
    r"(?:public|private|protected|static|final|\s)*function\s+(\w+)\s*\(", re.S)
CLASS_RE = re.compile(r"\b(?:final\s+|abstract\s+|readonly\s+)*class\s+(\w+)\s*(?:extends\s+([\w\\]+))?")
NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w\\]+)\s*;", re.M)

SIGNALS = {
    "db_integration": [r"\bKernelTestCase\b", r"\bWebTestCase\b", r"\bApiTestCase\b", r"\bTagTestCase\b",
                       r"\bDoctrineTestCase\b", r"wrapInRollback", r"\bEntityManager(?:Interface)?\b",
                       r"->beginTransaction\(", r"\bPdo[A-Z]\w*Repository\b", r"ResetDatabase",
                       r"\bFactories\b"],
    "kernel_boot": [r"static::createClient\s*\(", r"self::createClient\s*\(", r"::bootKernel\s*\(",
                    r"static::getContainer\s*\(", r"self::getContainer\s*\("],
    "factory": [r"\b\w+Factory::(?:createOne|createMany|new|createSequence|random\w*)\s*\("],
    "sleep": [r"\bsleep\s*\(", r"\busleep\s*\("],
    "network": [r"\bcurl_exec\s*\(", r"file_get_contents\s*\(\s*['\"]https?://",
                r"new\s+\\?GuzzleHttp\\?\\Client", r"HttpClient::create"],
    "filesystem": [r"\bfile_put_contents\s*\(", r"\bmkdir\s*\(", r"\bunlink\s*\(", r"sys_get_temp_dir"],
    "randomness": [r"\brand\s*\(", r"\bmt_rand\s*\(", r"\buniqid\s*\(", r"\brandom_int\s*\("],
    "time_dependency": [r"\bnew\s+\\?DateTime(?:Immutable)?\s*\(\s*\)", r"\btime\s*\(\s*\)", r"\bdate\s*\(",
                        r"['\"](?:now|today|tomorrow|yesterday)['\"]"],
    "skipped": [r"markTestSkipped", r"markTestIncomplete", r"@group\s+disabled"],
    "no_assertion_declared": [r"expectNotToPerformAssertions"],
    "sql_literal": [r"['\"]\s*(?:SELECT|INSERT|UPDATE|DELETE)\s", r"->executeQuery\s*\(", r"->executeStatement\s*\("],
    "reflection": [r"new\s+\\?ReflectionProperty", r"new\s+\\?ReflectionMethod", r"->setAccessible\s*\("],
}
METHOD_SIGNALS = ("db_integration", "kernel_boot", "factory", "sleep", "network", "filesystem",
                  "skipped", "randomness", "time_dependency", "sql_literal", "no_assertion_declared",
                  "reflection")
MOCK_RE = re.compile(r"createMock\s*\(|getMockBuilder\s*\(|createStub\s*\(|->prophesize\s*\(|createPartialMock\s*\(")
DATAPROVIDER_RE = re.compile(r"#\[DataProvider|@dataProvider")
TRIVIAL_ASSERT_RE = re.compile(
    r"assertTrue\s*\(\s*true\s*\)|assertSame\s*\(\s*(\d+|'[^']*')\s*,\s*\1\s*\)|"
    r"assertNotNull\s*\(\s*\$\w+\s*\)\s*;\s*\}", re.S)
TEST_ROOT_NAMES = {"tests", "test", "Test", "Tests"}


def naming_style(name: str, annotated: bool) -> str:
    if re.match(r"^test_?GIVEN_.+_WHEN_.+_THEN_", name, re.I):
        return "given_when_then"
    if re.match(r"^test_[a-z0-9_]+$", name):
        return "snake_test"
    if re.match(r"^test[A-Z]\w*$", name):
        return "camel_test"
    if annotated:
        return "attribute_only"
    return "other"


def split_methods(src: str):
    """Yield (name, is_test, annotated, start_line, body) for every method. Brace-matched."""
    for m in ANY_METHOD_RE.finditer(src):
        name = m.group(2)
        annotated = bool(m.group(1)) or "@test" in (m.group(0) or "")
        brace = src.find("{", m.end())
        if brace == -1:
            continue
        depth, i = 0, brace
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        is_test = annotated or name.lower().startswith("test")
        yield name, is_test, annotated, src.count("\n", 0, m.start()) + 1, src[brace:i + 1]


def count_asserts(body: str) -> int:
    return (len(ASSERT_RE.findall(body)) + len(SELF_ASSERT_RE.findall(body))
            + len(MOCK_EXPECT_RE.findall(body)))


def normalize(body: str) -> str:
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*//[^\n]*", "", body)
    return re.sub(r"\s+", " ", body).strip()


def count_signals(text: str, keys) -> dict:
    return {k: sum(len(re.findall(p, text, re.I)) for p in SIGNALS[k]) for k in keys}


def scan_file(path: Path, root: Path, times: dict, defects: dict) -> dict:
    src = path.read_text(encoding="utf-8", errors="replace")
    cls = CLASS_RE.search(src)
    ns = NAMESPACE_RE.search(src)
    fqcn = (ns.group(1) + "\\" if ns else "") + (cls.group(1) if cls else "")
    parsed = list(split_methods(src))
    asserting_helpers = {n for n, is_test, _, _, b in parsed if not is_test and count_asserts(b)}
    helper_call_re = (re.compile(r"\$this\s*->\s*(" + "|".join(map(re.escape, asserting_helpers)) + r")\s*\(")
                      if asserting_helpers else None)
    setup_m = next((b for n, _, _, _, b in parsed if n == "setUp"), "")

    methods = []
    for name, is_test, annotated, line, body in parsed:
        if not is_test:
            continue
        key = f"{fqcn}::{name}"
        seconds = times.get(key)
        if seconds is None:
            # data-provider variants are keyed "Class::method#0" / "Class::method with data set ..."
            variants = [v for k, v in times.items() if k.startswith(key + "#") or k.startswith(key + " with")]
            seconds = round(sum(variants), 4) if variants else None
        methods.append({
            "name": name,
            "line": line,
            "lines": body.count("\n") + 1,
            "assertions": count_asserts(body),
            "delegated_assertions": len(helper_call_re.findall(body)) if helper_call_re else 0,
            "mocks": len(MOCK_RE.findall(body)),
            "trivial_assert": bool(TRIVIAL_ASSERT_RE.search(body)),
            "naming_style": naming_style(name, annotated),
            "body_hash": hashlib.sha1(normalize(body).encode()).hexdigest()[:12],
            "seconds": seconds,
            "recent_defect": key in defects or any(k.startswith(key) for k in defects),
            "signals": count_signals(body, METHOD_SIGNALS),
        })
    known = [m["seconds"] for m in methods if m["seconds"] is not None]
    return {
        "path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
        "class": cls.group(1) if cls else None,
        "fqcn": fqcn or None,
        "extends": (cls.group(2) or "").lstrip("\\") if cls else None,
        "lines": src.count("\n") + 1,
        "data_providers": len(DATAPROVIDER_RE.findall(src)),
        "mocks": len(MOCK_RE.findall(src)),
        "setup": bool(setup_m),
        "setup_signals": count_signals(setup_m, ("db_integration", "kernel_boot", "factory")) if setup_m else {},
        "signals": count_signals(src, SIGNALS.keys()),
        "seconds_total": round(sum(known), 3) if known else None,
        "methods": methods,
    }


def load_timings(path: Path) -> tuple[dict, dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("times", {}), d.get("defects", {})


def find_test_root(target: Path) -> Path:
    for p in [target, *target.parents]:
        if p.name in TEST_ROOT_NAMES:
            return p
    return target if target.is_dir() else target.parent


GETTER_RE = re.compile(r"function\s+(?:get|is|has)[A-Z]\w*\s*\(")
PUBLIC_METHOD_RE = re.compile(r"public\s+(?:static\s+)?function\s+(?!__construct\b)(\w+)\s*\(")
ROUTE_RE = re.compile(r"#\[Route\(\s*(?:path:\s*)?['\"]([^'\"]+)['\"](?:[^)]*?name:\s*['\"]([^'\"]+)['\"])?", re.S)
PROP_ONLY_RE = re.compile(r"\b(?:final\s+)?readonly\s+class\b|\benum\s+\w+|\binterface\s+\w+|\btrait\s+\w+")


def classify_layer(rel: str) -> str:
    for layer in ("UI/Controller", "UI/Twig", "UI", "Application", "Domain", "Infrastructure"):
        if f"/{layer}/" in f"/{rel}":
            return layer
    return "other"


def route_hit(path: str, name: str, tests_blob: str) -> bool:
    if name and name in tests_blob:
        return True
    if "{" not in path:
        return path in tests_blob
    rx = re.sub(r"\\\{[^}]+\\\}", r"[^/'\"\\s]+", re.escape(path))
    return re.search(rx, tests_blob) is not None


def coverage_map(src_root: Path, test_root: Path, repo: Path) -> list[dict]:
    """Classes with behaviour whose short name never appears in any test source."""
    tests_blob = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                           for p in test_root.rglob("*.php"))
    names_in_tests = set(re.findall(r"\b[A-Z]\w+\b", tests_blob))
    untested = []
    for p in sorted(src_root.rglob("*.php")):
        src = p.read_text(encoding="utf-8", errors="replace")
        if PROP_ONLY_RE.search(src) and not re.search(r"\bclass\s+\w+", src.replace("readonly class", "")):
            continue
        cls = CLASS_RE.search(src)
        if not cls or "abstract class" in src:
            continue
        if PROP_ONLY_RE.search(src) and re.search(r"\breadonly\s+class\b", src):
            continue
        public = [m for m in PUBLIC_METHOD_RE.findall(src)]
        behaviour = [m for m in public if not re.match(r"^(get|is|has|set)[A-Z]", m)]
        if not behaviour:
            continue
        if cls.group(1) in names_in_tests:
            continue
        routes = ROUTE_RE.findall(src)
        if any(route_hit(path, name, tests_blob) for path, name in routes):
            continue
        rel = str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p)
        parts = p.relative_to(src_root).parts
        untested.append({
            "class": cls.group(1),
            "path": rel,
            "context": parts[0] if len(parts) > 1 else None,
            "layer": classify_layer(str(p.relative_to(src_root))),
            "public_methods": len(behaviour),
            "routes": [path for path, _ in routes],
            "is_message_handler": "#[AsMessageHandler" in src,
        })
    return untested


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--src")
    ap.add_argument("--timings")
    ap.add_argument("--db-base", action="append", default=[])
    a = ap.parse_args()

    for rx in a.db_base:
        SIGNALS["db_integration"].append(rx)

    target = Path(a.target).resolve()
    root = Path.cwd().resolve()
    files = sorted(target.rglob("*Test.php")) if target.is_dir() else [target]
    files = [f for f in files if "/vendor/" not in str(f) and "/node_modules/" not in str(f)]

    times, defects = load_timings(Path(a.timings)) if a.timings else ({}, {})
    scanned = [scan_file(f, root, times, defects) for f in files]

    dupes: dict[str, list[str]] = {}
    for f in scanned:
        for m in f["methods"]:
            if m["lines"] > 4:
                dupes.setdefault(m["body_hash"], []).append(f"{f['path']}::{m['name']}")
    duplicates = [{"hash": h, "occurrences": v} for h, v in dupes.items() if len(v) > 1]

    all_methods = [m for f in scanned for m in f["methods"]]
    timed = [(f["path"], m["name"], m["seconds"]) for f in scanned for m in f["methods"] if m["seconds"]]
    kernel_seconds = sum(m["seconds"] or 0 for f in scanned for m in f["methods"]
                         if f["signals"]["db_integration"] or f["signals"]["kernel_boot"])
    total_seconds = sum(s for _, _, s in timed)

    untested = coverage_map(Path(a.src).resolve(), find_test_root(target), root) if a.src else None

    out = {
        "target": str(target.relative_to(root)) if target.is_relative_to(root) else str(target),
        "timings_source": a.timings,
        "totals": {
            "files": len(scanned),
            "tests": len(all_methods),
            "assertions": sum(m["assertions"] for m in all_methods),
            "assertless_tests": sum(1 for m in all_methods
                                    if m["assertions"] == 0 and m["delegated_assertions"] == 0
                                    and not m["signals"]["no_assertion_declared"]),
            "trivial_tests": sum(1 for m in all_methods if m["trivial_assert"]),
            "db_touching_files": sum(1 for f in scanned if f["signals"]["db_integration"] or f["signals"]["kernel_boot"]),
            "kernel_boots": sum(m["signals"]["kernel_boot"] for m in all_methods),
            "sleep_calls": sum(f["signals"]["sleep"] for f in scanned),
            "network_calls": sum(f["signals"]["network"] for f in scanned),
            "skipped": sum(f["signals"]["skipped"] for f in scanned),
            "naming_styles": dict(Counter(m["naming_style"] for m in all_methods)),
            "mocks": sum(f["mocks"] for f in scanned),
            "duplicate_bodies": len(duplicates),
            "timed_tests": len(timed),
            "seconds_total": round(total_seconds, 2),
            "seconds_kernel_or_db": round(kernel_seconds, 2),
            "slowest": [{"path": p, "test": n, "seconds": round(s, 3)}
                        for p, n, s in sorted(timed, key=lambda t: -t[2])[:20]],
            "slowest_files": [{"path": f["path"], "seconds": f["seconds_total"], "tests": len(f["methods"])}
                              for f in sorted((x for x in scanned if x["seconds_total"]),
                                              key=lambda x: -x["seconds_total"])[:10]],
            "recent_defects": sum(1 for m in all_methods if m["recent_defect"]),
            "untested_by_layer": dict(Counter(u["layer"] for u in untested)) if untested is not None else None,
        },
        "duplicates": duplicates,
        "untested": untested,
        "files": scanned,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
