# HTML Report Format

The review is one self-contained HTML file in the OS temp directory (`$TMPDIR`, fallback `/tmp`): `<tmpdir>/functional-tests-review-<timestamp>.html`. Tailwind and Mermaid come from CDNs. Mermaid for graph-shaped relationships (test → interface → module, seam with two adapters); hand-built divs for time bars and mass diagrams. Mix them — an all-Mermaid report looks generic.

Written in the user's language (French for this user). Architecture and test nouns come from [LANGUAGE.md](LANGUAGE.md) untranslated where the French would be ambiguous: *module, interface, seam, adapter, fake, test miroir, test de passage, trou de couverture*.

## Scaffold

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <title>Revue des tests fonctionnels — {{repo}} · {{cible}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      .seam { stroke-dasharray: 4 4; }
      .gap  { background: repeating-linear-gradient(45deg,#fee2e2 0 6px,#fff 6px 12px); }
      .deep { background: linear-gradient(135deg,#0f172a,#1e293b); color:#f8fafc; }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>…</header>
      <section id="candidates" class="space-y-10">…</section>
      <section id="top-recommendation">…</section>
    </main>
  </body>
</html>
```

## Header

Repo, target path, date, timings source (or "durées non mesurées"). Then **three counters** in a row of cards, not a score:

- **Tests supprimables** — count of `useless` findings' tests
- **Modules non couverts** — count of confirmed `coverage` findings
- **Secondes récupérables** — sum of quantified `perf` savings, with the suite's measured total beside it (e.g. `≈ 6,1 s sur 17,1 s`)

Below: a compact legend — solid box = module, dashed line = seam, hatched red = coverage gap, dark box = deep module tested at its interface. No introduction paragraph.

## Candidate card

Each candidate is one `<article>` with an `id` (for the top-recommendation anchor). Diagrams carry the weight; prose is sparse.

- **Title** — imperative, names the change: « Supprimer les 6 tests miroir de `ReminderDraft` », « Couvrir `SendReminderCampaign` à son interface », « Un seul boot pour les 25 assertions de `ReminderControllerTest` ».
- **Badge row** — strength (`Strong` emerald, `Worth exploring` amber, `Speculative` slate) · lens tag (`useless` / `coverage` / `practice` / `perf` / `db` / `inmemory` / `flaky`) · severity · effort `S/M/L` · seconds when measured.
- **Fichiers** — `font-mono text-sm` list, test files and the module under test.
- **Avant / Après** — two columns, the centrepiece. Patterns below.
- **Problème** — one sentence. For `useless`: the bug that would *not* go uncaught if deleted (i.e. why nothing is lost). For `coverage`: the bug that goes uncaught today.
- **Solution** — one sentence, the exact edit: which tests go, which single test is added at which interface, which fixtures/fakes it needs.
- **Gains** — bullets ≤ 6 words, in glossary terms: « locality : un seul point de vérité », « leverage : 1 interface, 4 comportements », « −4,2 s mesurées », « 6 tests miroir en moins ».
- **ADR callout** (if it contradicts one) — one line, amber box.

If the diagram needs a paragraph, redraw the diagram.

## Diagram patterns by lens

### Supprimer (`useless`) — call-graph collapse
Before: N small test boxes each pointing at a getter / a mock call of the module (thin arrows). After: one dark deep box (module + interface label) with a single test box crossing its interface; the former tests faded inside with a strike-through.

### Couvrir (`coverage`) — seam crossing
Before: the module box hatched red (`.gap`), no arrow reaches it; its callers shown grey. After: Mermaid `flowchart LR`: `Test fonctionnel --> Interface(route / __invoke) --> Module`, with the outcome asserted as a note node (`302 + Reminder SENT + EmailSend créé`).

```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      T[SendReminderCampaignTest] -->|"__invoke(clients[])"| I{{"interface"}}
      I --> M[SendReminderCampaign]
      M --> O["1 ReminderOutcome par client"]
      classDef deep fill:#0f172a,color:#f8fafc,stroke:#0f172a;
      class M deep
  </pre>
</div>
```

### Accélérer (`perf`) — time bars
Two horizontal bars, widths proportional to **measured** seconds (Tailwind `w-[62%]` computed from the numbers), labelled with the seconds. Before: one bar segmented per kernel boot (25 thin segments). After: one segment. Put the recovered seconds in the badge row too.

### Fake au seam (`inmemory`) — two adapters
A dashed vertical seam line. Left: the module. Right, top: `DoctrineXRepository` (prod). Right, bottom: `InMemoryXRepository` (tests). Before shows the tests wired to the Doctrine adapter through the kernel; after shows them wired to the fake with the kernel box removed.

### Stabiliser (`flaky`) — sequence
Mermaid `sequenceDiagram`: the test, the module, the wall clock / RNG / previous test. Before: arrow from `Horloge système` into the module. After: `MockClock` injected at the seam.

### Pratiques (`practice`) — before/after code
Two `<pre class="text-xs">` blocks side by side: the smell and the fix (e.g. 5 near-identical tests → one `#[DataProvider]`). Only lens where code beats a diagram.

## Style

- Editorial, generous whitespace, `font-serif` optional for h1/h2 with stone/slate.
- One accent (emerald) plus red for gaps and amber for warnings.
- Diagrams ≈ 320 px tall so before/after sit side by side without scrolling.
- `text-xs uppercase tracking-wider` for labels inside diagrams.
- Only scripts: Tailwind CDN and the Mermaid import. No app code.

## Top recommendation

One larger card at the end: the candidate that makes the most other candidates cheap or moot, one sentence why, an anchor to its card, and a suggested order (« 3 → 1 → 5, puis décider 7 »). If no candidate dominates, say so and pick the highest severity × (1/effort).

## Tone

Plain, concise, no hedging, no « il est à noter que ». Glossary terms exactly ([LANGUAGE.md](LANGUAGE.md)): module, interface, seam, adapter, fake, test fonctionnel, test miroir, test de passage, trou de couverture, coût d'exécution. Never « unit test », « composant », « service », « helper », « boundary », « plus propre », « plus maintenable ».
