---
name: improve-functional-tests
description: >-
  Use when the user wants to improve an existing PHPUnit suite — delete useless
  tests, close functional coverage gaps, or make the suite run faster. Triggers:
  "améliorer les tests", "tests inutiles", "quels tests supprimer", "couverture
  fonctionnelle", "ce qui n'est pas testé", "tests lents", "suite trop lente",
  "accélérer les tests", "trop d'accès DB dans les tests", "candidat InMemory",
  "audit tests", "qualité des tests", "improve tests", "test audit". Also use
  when a feature was just finished and the user asks whether its tests are worth
  anything, or when a CI test stage got slow and nobody knows why. Scans a
  directory of tests plus the production code it should cover, reads the real
  per-test timings from PHPUnit's cache, and produces a self-contained HTML
  review of candidates (delete / cover / speed up / fake at the seam) with
  before/after diagrams and one top recommendation. Read-only until the user
  picks candidates. PHPUnit only.
user-invocable: true
auto-trigger: false
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
---

# Improve Functional Tests

Surface the tests that catch nothing, the modules nothing tests, and the seconds the suite wastes — then propose the smallest set of changes that fixes all three. Sibling of `improve-codebase-architecture`: same vocabulary, same report shape, same grilling loop. The aim is a suite where **every test crosses a module's interface and would go red on a plausible bug**, and nothing else.

## Glossary

Use these terms exactly. Full definitions in [LANGUAGE.md](LANGUAGE.md).

- **Module / Interface / Implementation / Seam / Adapter / Depth / Leverage / Locality** — as in `improve-codebase-architecture`.
- **Functional test** — crosses the interface, asserts a business-observable outcome, survives refactors.
- **Mirror test** — restates its own arrangement. Catches nothing.
- **Pass-through test** — tests a module that only delegates. Deletion test applied to tests.
- **Coverage gap** — a module with behaviour whose interface no test crosses. Measured on interfaces, not lines.
- **Execution cost** — real seconds from PHPUnit's cache, never estimated.
- **Fake** — in-memory adapter at a Domain seam. Two adapters make a seam real.

Core rule: **a test has value only if some plausible production bug makes it fail.** Before proposing a deletion, name the bug that would go uncaught. If you can, it is a weak test to strengthen.

## Process

### 1. Discover the project's conventions

Never assume a base class, a naming style or a fixture library. Read, in this order:

- `phpunit*.xml` — test suites, bootstrap, `<extensions>` (`DAMA\DoctrineTestBundle` → rollback is handled, never flag it; `Foundry` → factories exist).
- `tests/bootstrap.php`, the project's `AGENTS.md`/`CLAUDE.md` Testing section, `CONTEXT.md` (domain vocabulary for naming candidates), `docs/adr/` (decisions not to re-litigate).
- Existing fakes: `grep -rlE "class (InMemory|Fake)\w+" tests/`.
- Runner: `Makefile` / `composer.json` scripts (`make test c="…"`, `bin/phpunit`, docker wrapper).

Confirm the target as a repo-relative path — a bounded context's test directory is the ideal grain (`tests/Receivables`). If not given, list candidates and ask. Over 400 test files: say the scan is coarse and propose narrowing.

### 2. Scan — measurable signals

Run the collector from the repo root; never re-implement it inline:

```bash
python3 <skill-dir>/scan.py <target> --src src --timings .phpunit.cache/test-run-history > <scratchpad>/tests-scan.json
```

`--timings` accepts `test-run-history` or `test-results` (PHPUnit cache v2). If neither exists, run the target suite once with the project runner, then re-scan; if that is impossible, proceed and mark perf findings "not measured". `--src` roots the coverage map; `--db-base REGEX` adds a project-specific kernel/DB base class.

The JSON gives per test: assertions (incl. delegated helpers and mock expectations), `seconds`, `recent_defect`, naming style, `kernel_boot`/`factory`/`db_integration`/`time_dependency` signals, duplicate body hashes; per suite: `totals.slowest`, `slowest_files`, `naming_styles`, `seconds_kernel_or_db`; and `untested` — production classes with behaviour whose name, route path and route name appear in no test.

The scan is **evidence, not verdict**. Every finding is confirmed by reading code.

### 3. Explore

Use the Agent tool with `subagent_type=Explore`, up to three in parallel, each with a focus:

- **Suspects**: tests with `assertions == 0 && delegated_assertions == 0 && !no_assertion_declared`, `trivial_assert`, duplicate groups, `mocks >= 5`, `reflection`.
- **Gaps**: `untested` entries in the target's context, ranked money → outbound side effects → auth → persistence invariants → display. Open each class: does another class's test reach it through its interface?
- **Cost**: `totals.slowest` (> 1 s) and `slowest_files` (> 5 s); for each, what dominates — boots, fixtures, I/O, loops? For kernel tests: is the assertion about the route, or about a use case with its own interface?

Cap 40 files read; if the scan exceeds that, take the highest-signal 40 and report the truncation as a `low` finding. Note friction as you go: where does one behaviour need five tests? Where does a test read the implementation instead of the interface? Where does a pure module pay for a kernel?

### 4. Judge — the seven lenses

Apply [LENSES.md](LENSES.md): `useless`, `coverage`, `practice`, `perf`, `db`, `inmemory`, `flaky`. Each candidate becomes a card: **Files · Problem · Solution · Wins · Before/After · Strength** (`Strong` / `Worth exploring` / `Speculative`), plus severity and effort. Group: one fake = one finding for all tests behind that seam; naming = one finding per file; one page = one perf finding for all its boots.

### 5. Report — self-contained HTML

Write `<tmpdir>/functional-tests-review-<timestamp>.html` (`$TMPDIR`, fallback `/tmp`) following [HTML-REPORT.md](HTML-REPORT.md): Tailwind + Mermaid via CDN, three counters in the header (**tests supprimables · modules non couverts · secondes récupérables**), one card per candidate with a before/after diagram, and a closing **Top recommendation** — the change that makes the most other candidates cheap or moot, with a suggested order.

Open it (`open` on macOS, `xdg-open` on Linux), give the absolute path, print the top 5 candidates as a numbered list, and ask: **« Lesquels veux-tu explorer ? »** Do not edit anything yet.

### 6. Grilling loop

When the user picks a candidate, walk it with them: the bug that goes uncaught today, the interface the new test crosses, which existing tests survive, what fixtures or fake it needs, the seconds it recovers. Side effects happen inline:

- Naming a module or outcome after a concept absent from `CONTEXT.md` → add the term (create the file lazily; format in `grill-with-docs/CONTEXT-FORMAT.md`).
- A fake becomes a seam-placement question → `improve-codebase-architecture/DEEPENING.md` and `INTERFACE-DESIGN.md`.
- User rejects a candidate for a load-bearing reason → offer an ADR (`grill-with-docs/ADR-FORMAT.md`) so future reviews don't re-suggest it. Skip ephemeral reasons.

### 7. Apply — opt-in only

Only for candidates the user named. Then:

1. Baseline: run the **target** suite with the project runner. Red before the edit → stop and report.
2. One candidate at a time. A deletion leaves the rest green; a kernel→pure move or DB→fake swap keeps the same assertions passing; a new functional test goes red when its module is broken (mutate once to prove it, then restore).
3. After each edit re-run **only the touched test files**, not the whole suite. Run the full target suite once at the end.
4. A deletion that turns another test red exposed shared state — revert, file a `flaky` finding.
5. Never commit. Hand the diff to the user, with recovered seconds measured, not estimated.

## Pitfalls

| Rationalisation | Why it's wrong | Counter |
|---|---|---|
| "Few files, I'll skip the scan" | Duplicates, delegated assertions and real seconds are invisible by eye | Step 2 is not optional |
| "0 assertions but it checks nothing crashes" | Then it must say so with `expectNotToPerformAssertions` | Name the uncaught bug first |
| "It boots the kernel, so it's slow" | 40 ms kernel tests exist; 3 s pure tests exist | Quote `seconds` or say "not measured" |
| "Untested class → write a test per method" | Tests past the interface break on refactor | One functional test at the interface |
| "InMemory everywhere" | A fake for one test costs more than it saves | Four conditions, `low` under 3 tests |
| "Missing rollback" with DAMA present | DAMA wraps every test in a transaction | Discovery step decides |
| "I'll delete the useless ones while I'm here" | Unvalidated deletion is an invisible loss of safety net | Step 7, opt-in, no commit |

## Quality gates

- [ ] Conventions discovered from the project, none assumed (base classes, naming, rollback, fakes, runner)
- [ ] `scan.py` run with `--src` and `--timings` (or "not measured" stated) before any judgment
- [ ] Every finding cites a real test or a real untested class that was opened
- [ ] Every `useless` finding names the bug that would *not* go uncaught after deletion
- [ ] Every `coverage` finding names the interface to test and the outcome to assert
- [ ] Every `perf` finding quotes measured seconds and the seconds it recovers
- [ ] Every `inmemory` finding verifies the Domain interface exists and counts the tests it unlocks
- [ ] Naming reported against the majority style, aggregated per file
- [ ] HTML in the temp dir, opened, path given; three counters; one Top recommendation
- [ ] Truncation reported as a finding
- [ ] Zero repo files modified before the user picks candidates in Step 7

## Exit protocol

```
REVUE TESTS FONCTIONNELS — {target}

Scan :        {files} fichiers · {tests} tests · {seconds_total} s mesurées ({timed}/{tests} chronométrés)
Supprimables : {n} tests miroir / de passage
Non couverts : {n} modules ({money} argent · {side_effects} effets de bord · {auth} auth)
Récupérables : ≈ {n} s ({pct} % du total)

Top 5 :
  1. [{strength}/{sev}/{effort}] {title} — {file}
  2. …

Rapport : {absolute html path}
Lesquels veux-tu explorer ?
```
