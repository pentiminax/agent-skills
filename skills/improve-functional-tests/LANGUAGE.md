# Language

Shared vocabulary for every finding this skill makes. Use these terms exactly — don't drift into "unit test", "component", "service", "helper", "boundary". Consistent language is the point.

The architecture terms are the same as in `improve-codebase-architecture/LANGUAGE.md`; the test terms extend them.

## Architecture terms (shared)

**Module** — anything with an interface and an implementation: a function, a class, a use case, a controller, a bounded context. _Avoid_: unit, component, service.

**Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, configuration. For a controller the interface is the route (method, path, form fields, status codes). For a use case it is `__invoke` / `handle` plus its Command. _Avoid_: API, signature.

**Implementation** — the code inside the module. Private methods, collaborators, SQL.

**Seam** — the place where an interface lives; where behaviour can be swapped without editing in place. A repository interface in `Domain/Repository/` is a seam. _Avoid_: boundary.

**Adapter** — a concrete thing satisfying an interface at a seam. Doctrine repository in production; a fake in tests.

**Depth / deep / shallow** — leverage at the interface. A deep module hides a lot of behaviour behind a small interface. A shallow module's interface is nearly as complex as its implementation.

**Leverage** — what callers and tests get from depth: one interface exercised, many behaviours verified.

**Locality** — what maintainers get from depth: change, bugs and verification concentrate in one place.

## Test terms

**Functional test**
A test that crosses a module's interface and asserts a business-observable outcome: the response of a route, the state a use case leaves behind, the message it dispatches, the outcome value it returns. It survives an internal refactor untouched. This is the test the skill tries to *add* and *keep*.
_Avoid_: integration test, unit test (they describe setup cost, not value).

**Mirror test**
An assertion that restates the arrangement: a getter returns what the constructor was handed; a mock is asserted to have been called with what the test itself passed in; `assertTrue(true)`. No plausible production bug turns it red. Deletion candidate.

**Pass-through test**
A test of a shallow module that only delegates. Apply the deletion test to the *test*: delete it — if the behaviour is already verified by a functional test at the deeper module's interface, nothing is lost. If not, the finding is a coverage gap at the deeper module, not a reason to keep the pass-through test.

**Coverage gap**
A module with behaviour (at least one public method that is not a getter/setter) whose interface no test crosses. Detected by `scan.untested`: the class name, its route path and its route name never appear in any test source. Measured on interfaces, never on lines.

**Execution cost**
Real seconds from PHPUnit's cache (`.phpunit.cache/test-run-history`, key `times`). Never estimated from line count, mock count or "it boots the kernel". A finding in the `perf` lens quotes seconds and names the seconds it would recover.

**Kernel test**
A test that boots the Symfony kernel or the HTTP client (`KernelTestCase`, `WebTestCase`, `createClient()`, `bootKernel()`). Necessary when the interface *is* the route. Pure cost when the assertion is about a use case that has its own interface.

**Fake**
An in-memory adapter satisfying a Domain repository interface (`InMemoryXRepository`). Two adapters (Doctrine in production, fake in tests) make the seam real; one adapter is only indirection. A fake serving fewer than three tests is not yet worth its maintenance.

**Signal**
A measurable fact from `scan.py` (assertion count, seconds, kernel boots, duplicate hash). A signal is evidence, never a verdict. Every finding is confirmed by reading the test.

## Principles

- **A test has value only if some plausible production bug makes it fail.** Coverage %, assertion count and line count are proxies, not value. Before proposing a deletion, name the bug that would go uncaught. If you can name one, the test is weak, not useless — strengthen it.
- **The interface is the test surface.** Test a module through its interface. A test that reaches into the implementation (reflection, private state, mock-call ordering) is testing past the interface and will break on the next refactor.
- **Deletion test, applied to tests.** Imagine deleting the test. If no behaviour becomes unverified, it was a mirror or pass-through. If a behaviour becomes unverified, it earns its keep — or points at where a functional test should live.
- **Cost is measured, not assumed.** A kernel test that runs in 40 ms is not a perf finding. A pure test with a 3-second Foundry `setUp` is.
- **One fake, N tests.** Introduce a fake when it unlocks several tests behind the same seam, never for one.

## Rejected framings

- **"Unit vs integration"** as the axis of quality — it describes setup, not whether a bug would be caught. Use functional test / mirror test / pass-through test.
- **Coverage percentage as a target** — rewards mirror tests. Use coverage gap (interfaces crossed by zero tests).
- **"Slow test" by intuition** — use `seconds` from the cache or say "not measured".
