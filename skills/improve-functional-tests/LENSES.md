# Lenses

Apply every lens to every test read in the Explore step, and lens 2 to every entry of `scan.untested` in scope. A finding needs a named test (or a named untested module) and a concrete reason — never "could be improved". Vocabulary: [LANGUAGE.md](LANGUAGE.md).

Severity: `high` = misleading or harmful (false confidence, flake, deletion candidate, uncovered money/auth path). `medium` = real cost with no benefit (needless kernel, duplication, slowness, uncovered secondary path). `low` = style, naming, polish. Effort: `S` (< 15 min), `M` (< 1 h), `L` (more). Recommendation strength: `Strong` / `Worth exploring` / `Speculative`.

## 1. Useless (`useless`) — mirror and pass-through tests

Deletion candidates:

- No assertion, and no `expectNotToPerformAssertions`, and no delegated assertion (`assertions == 0 && delegated_assertions == 0 && signals.no_assertion_declared == 0`). Assertions in a *parent* class helper are the scan's blind spot — read the file.
- Only `assertTrue(true)` / `assertNotNull($x)` on something the constructor guarantees.
- Getter returns what the constructor was handed (tests the language, not the domain).
- Mock asserted to have been called with what the test itself passed in.
- Byte-identical to another test (`duplicates`) with no differing input.
- `markTestSkipped` / `markTestIncomplete` without a ticket reference.
- Asserts framework or library behaviour, not project code.
- Pass-through: the module under test only delegates and the deeper module already has a functional test. If the deeper module has none, file a lens-2 finding instead and keep the test until then.

Before proposing a deletion, state the bug that *would* go uncaught. If you can name one, it is a weak test to strengthen, not a deletion.

## 2. Coverage gap (`coverage`) — new

Source: `scan.untested`, filtered to the target's bounded context(s). Confirm each one by opening the class: the scan ignores getters/setters and route names but cannot see a test that reaches the module through another class's interface (e.g. a Twig component rendered by a controller test).

Rank by what breaks silently:

1. Money (`bcmath`, prices, margins, totals, payment links)
2. Outbound side effects (Sage push, email send, Mercure publish, external HTTP)
3. Authentication / authorization (voters, `IsGranted`, role checks)
4. Persistence with invariants (unique constraints, state transitions)
5. Everything else (listing, display, formatting)

Solution shape: **one functional test at the interface** — a `WebTestCase` request for a route, an `__invoke`/`handle` call for a use case or message handler, a `render` for a Twig component. Never one test per private method. Name the outcome to assert (status code + persisted state + dispatched message), and the fixtures needed (existing Foundry factory? existing fake?).

A controller whose only behaviour is `render(...)` with a repository read is `low`. A handler that writes to Sage or sends money is `high`.

## 3. Practice (`practice`)

- Naming: the majority style in `totals.naming_styles` is the convention. Report the minority style as **one aggregated finding per file**, never one per method. If two styles are near-equal, report nothing — that is a project decision, not a defect.
- Several unrelated behaviours asserted in one method.
- Assertions inside loops or conditionals (a failure cannot be located).
- Logic in the test (branching, computation) that mirrors the implementation.
- Over-mocking: mocking value objects, DTOs, or the module under test.
- `setUp` building state most tests in the file don't use (`setup_signals` with `factory`/`kernel_boot` > 0 in a file where most tests are pure).
- Near-identical tests that should be one `#[DataProvider]`.
- Assertions on private state through reflection (`signals.reflection`).
- **Neutralised assertion hook by inheritance**: a subclass (`extends` another `*Test`) overriding a parent assertion hook with an empty body. Diff the overridden methods.

## 4. Performance (`perf`) — measured

Requires `--timings`. Without it, say "not measured" and only report `sleep`/network/filesystem signals.

Findings, each quoting seconds:

- Any test `> 1 s` (`totals.slowest`). Open it: what dominates — fixtures, kernel boot, real I/O, a loop?
- Any file `> 5 s` cumulative (`totals.slowest_files`). Count `kernel_boot` per method: N tests that each boot a client to assert one aspect of the *same page* collapse into one request with N assertions, or into a `#[DataProvider]` over one booted client.
- `seconds_kernel_or_db / seconds_total` > 80 %: the suite pays for the kernel everywhere. For each kernel test, ask: is the assertion about the *route* (status, redirect, rendered HTML) or about a *use case* that has its own interface? The latter moves to a pure test through the use case interface — name the interface.
- Heavy Foundry `setUp` (`setup_signals.factory` ≥ 3) in a file whose tests mostly don't read those fixtures.
- `sleep`/`usleep` → clock abstraction (`ClockInterface` + `MockClock`) or an event assertion.
- Real HTTP → stubbed client. Filesystem outside a temp dir → temp dir + `tearDown`.
- Loops running hundreds of iterations to assert one invariant.

Suite-level levers (one finding, `Speculative` unless timings prove it): `#[Group('slow')]` for tests > 1 s run in a separate CI job; `--order-by=defects` locally; parallel runner (`paratest`) if absent from `vendor/bin` and the DB layer supports it (DAMA + per-process DB).

**Quantify**: "recovers ~4.2 s of 9.8 s in `ReminderControllerTest`" — not "faster".

## 5. Database (`db`)

For every test with `db_integration` or `kernel_boot` signals: *does the assertion depend on persistence semantics?* (transaction, unique constraint, real SQL, cascade, isolation, Doctrine hydration). Yes → legitimate, no finding. No → the DB is pure cost; file under lens 4 with seconds, or lens 6 if a seam exists.

Missing rollback is a finding **only** when the discovery step found no rollback extension (`DAMA\DoctrineTestBundle`, `ResetDatabase`, project `wrapInRollback`). With DAMA present, never flag it.

## 6. Fake at the seam (`inmemory`)

Propose a fake only when all four hold:

1. The module under test depends on a **repository interface in Domain** (grep the interface path), not on a concrete Doctrine/PDO class.
2. The tests assert domain behaviour, not persistence behaviour.
3. The operations used are array-storable (find/save/delete/list) — no raw SQL, no query builder.
4. A fake for that interface already exists (discovery step: `InMemory*` / `Fake*` under `tests/`) or costs under ~50 lines.

Name the existing fake if any; otherwise sketch the interface methods. Group all tests behind one interface into **one finding** — one fake unlocks all of them. Fewer than three tests → `low`. When the candidate turns into a seam-placement question, use `improve-codebase-architecture/DEEPENING.md`.

## 7. Flaky (`flaky`)

- `new DateTime()` / `time()` / `'now'` without injected clock (`signals.time_dependency`). Project rule: `ClockInterface`.
- `rand`/`uniqid` in assertions rather than in irrelevant fixture noise.
- Order dependency: a test relying on state left by a previous test — confirm by reading, and by `recent_defect` (the test was red in a recent run).
- Assertions on unordered collections without sorting.
- `recent_defects` from the PHPUnit cache: a test that was recently red while its code did not change is a flake signal, not proof. Say which.
