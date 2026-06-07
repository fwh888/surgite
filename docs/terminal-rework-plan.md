# Terminal Aesthetic Rework + Multi-Theme Plan

Status: **Draft for review** · Target: a 0.2.0 "look & feel" milestone

Reframe the web UI as a **pseudo-terminal** — monospace, terminal-window chrome,
command-style interactions — and replace the single light/dark toggle with a set of
**colorschemes** (Light, GitHub Dark, Nord, Catppuccin Mocha, Solarized Dark). The
app is a CLI tool at heart, so a terminal skin is thematically honest and gives it
real personality. Inspiration: [hugo-theme-terminal](https://panr.github.io/hugo-theme-terminal-demo/).

This supersedes the plain "dark mode shouldn't be purple + add themes" request — the
themes become terminal colorschemes, which is a cleaner framing.

---

## 1. Architecture — token-based theming (the refactor)

Today every component hardcodes Tailwind `slate-*` / `indigo-*` classes with `dark:`
variants. That can't scale past two themes. We move to **semantic CSS custom
properties**, set per theme and switched by a `data-theme` attribute on `<html>`.

Semantic tokens (defined once, themed per colorscheme):

| Token | Role |
| --- | --- |
| `--bg` | page background |
| `--surface` | cards, inputs |
| `--surface-2` | subtle bars / card headers |
| `--border` / `--border-subtle` | borders |
| `--fg` / `--fg-muted` / `--fg-faint` | text tiers |
| `--accent` / `--accent-hover` / `--accent-contrast` | primary action + focus ring + text on accent |
| `--ok` / `--err` / `--warn` | success / error / warning (log lines, toasts) |

Tailwind v4 exposes these as utilities via `@theme inline`:

```css
@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-fg: var(--fg);
  --color-accent: var(--accent);
  /* … */
}
```

So components use `bg-surface`, `text-fg`, `border-border`, `text-accent` etc., and
the colors follow whatever `data-theme` is active. The `dark:` variants and the
`.dark` class go away.

**State model:** `theme.svelte.ts` changes from `'light' | 'dark'` to a theme **name**
(e.g. `'nord'`), persisted to localStorage. The pre-paint script in `app.html` sets
`data-theme` (and `color-scheme`) before first paint to stay flash-free. Each theme
declares `color-scheme: light|dark` so native controls (the date inputs) render right.

## 2. Colorschemes

Canonical palettes (so they look "right" to people who know them):

- **Light** — clean GitHub-light-style: `#ffffff` bg, `#1f2328` text, `#0969da` accent.
- **GitHub Dark** — `#0d1117` bg, `#161b22` surface, `#30363d` border, `#e6edf3` text,
  `#2f81f7` accent, `#3fb950`/`#f85149` ok/err. (Replaces the current purple dark.)
- **Nord** — `#2e3440` bg, `#3b4252` surface, `#d8dee9` text, `#88c0d0` accent.
- **Catppuccin Mocha** — `#1e1e2e` bg, `#313244` surface, `#cdd6f4` text, `#89b4fa` accent.
- **Solarized Dark** — `#002b36` bg, `#073642` surface, `#839496` text, `#268bd2` accent.
- *(optional 6th)* **Terminal** — the classic: near-black `#0c0c0c` bg, phosphor green
  `#33ff33` (or amber `#ffb000`) text/accent. Maximally on-theme; great default.

> Note: Solarized is intentionally low-contrast — we'll verify it still meets a
> reasonable contrast bar, and bump `--fg` toward `base1` if needed.

## 3. The terminal look (core treatment)

- **Monospace everywhere.** Ship a real mono webfont (proposal: **JetBrains Mono** via
  `@fontsource`, self-hosted so the app stays offline-friendly), fallback
  `ui-monospace, "SF Mono", Menlo, monospace`. Optional: enable ligatures.
- **Window chrome.** Wrap the app in a terminal "window": a title bar with the classic
  three traffic-light dots (●●●) and a title like `nick@standup: ~/standup`. Sharp
  1px borders, no rounded-2xl cards — boxy, framed panels.
- **Prompt-style section headers.** `~/repos ❯` and `~/summary ❯` instead of the
  plain uppercase labels.
- **Commands, not buttons.** Primary actions read as commands: `❯ generate`,
  `❯ add-repo`, `❯ ingest --all`. The add-repo input gets a `❯ ` prompt prefix.
- **Dashed separators** under headings (the hugo-theme touch).
- **Blinking block cursor** `█` after the header title / in focused inputs.

## 4. Personality & fun (the good stuff)

Grouped by how far to push it. ✅ = recommended core, ➕ = nice optional, 🥚 = easter egg.

- ✅ **CLI command echo.** Above each generated summary, show the equivalent CLI:
  `$ standup --repo foo --since 7.days.ago --summarize --provider deepseek`. On-theme
  *and* genuinely useful — it teaches the CLI and is copy-pasteable.
- ✅ **Toasts as log lines.** `[ ok ] ingested 12 commits` / `[fail] …` / `[warn] …`
  in mono with colored brackets, instead of the rounded pill toasts.
- ✅ **Status bar.** A pinned tmux/vim-style bottom bar: `[standup] scheme: nord │ 3
  repos │ last ingest 5m ago │ v0.2.0`. Useful and very on-theme.
- ✅ **Themed spinners.** Braille spinner `⣾⣽⣻⢿⡿⣟⣯⣷` for "generating…", and an ingest
  progress feel like `[####------]`.
- ➕ **`:colorscheme` picker.** The theme control opens a vim-style command line
  (`:colorscheme ▏`) listing the schemes — power-user wink. (Falls back to the plain
  dropdown you picked; we can do dropdown styled as a terminal menu and label it
  `:colorscheme`.)
- ➕ **Boot sequence.** On first load, the header "types" itself (`standup█`) or a one-
  line fake boot (`standup v0.2.0 — ready.`). Subtle, skippable.
- ➕ **Typewriter reveal** of the AI summary as it appears.
- 🥚 **`help` / `:help`** opens a man-page-style overlay of what the app does.
- 🥚 **Konami code** flips on a subtle CRT/scanline overlay (and `:set nocrt` off).
- 🥚 **`whoami`** prints `STANDUP_USER`; a `sudo` joke; an ASCII `figlet` banner of
  "standup" in an about/help screen.

**Guardrails:** honor `prefers-reduced-motion` (no blink/typewriter/CRT when set);
keep the keyboard-focus rings from the a11y pass; verify contrast per scheme; mono
body text needs comfortable line-height.

## 5. Component-by-component

- `app.html` — pre-paint `data-theme` + `color-scheme`; load the mono font.
- `layout.css` — token definitions per `[data-theme]`, `@theme inline` mapping, mono
  font-family on `body`, focus ring → `--accent`.
- `theme.svelte.ts` — name-based theme store + the theme list/metadata.
- New `ThemePicker.svelte` (replaces `ThemeToggle.svelte`) — the `:colorscheme` menu.
- New `WindowChrome.svelte` / status bar / log-line `Toaster` restyle.
- `+page.svelte` — window frame, prompt headers, command buttons, CLI echo.
- `RepoList`, `AddRepoForm`, `SummaryPanel`, `SummaryCard` — retoken + prompt/command
  styling; `SummaryCard` keeps copy/download, restyled.
- Favicon/logo — swap the "summary lines" mark for a `>_` prompt glyph (still themeable).

## 6. Delivery

Big change; suggest **two PRs** for reviewable diffs (or one if preferred):

1. **`feat: terminal theme foundation`** — token refactor, mono font, the 5–6
   colorschemes, the new theme picker, retokened components. (Delivers the original
   "GitHub dark + themes" ask on a mono terminal base.)
2. **`feat: terminal personality`** — window chrome, prompt/command styling, status
   bar, log-line toasts, CLI echo, spinners, and whichever ➕/🥚 items are chosen.

CHANGELOG `[Unreleased]` gets the entries; this all lands in the 0.2.0 cycle.

## 7. Decisions (locked)

- **Schemes (6):** Light, **GitHub Dark (default)**, Nord, Catppuccin Mocha,
  Solarized Dark, and a classic green/amber **Terminal** scheme (not default).
- **Personality in scope:** all ✅ core items (CLI echo, log-line toasts, status bar,
  spinners) **plus** ➕ typewriter summary reveal and 🥚 easter eggs (`help`/`:help`,
  Konami→CRT, `whoami`, ASCII banner). *Out:* the `:colorscheme` vim picker (use the
  terminal-styled dropdown) and the boot/typing intro.
- **Font:** JetBrains Mono (self-hosted via `@fontsource-variable`).
- **Delivery:** one PR.
