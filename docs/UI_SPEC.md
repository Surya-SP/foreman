# UI Design System (Foreman default)

Agents must follow this file for every Flutter app built with Foreman.
Product-specific overrides live in `tasks/design_language.md` (after design approve).
When they conflict, **design_language wins** for tokens; **this file wins** for kit rules.

## Stack

| Layer | Choice | Rule |
|-------|--------|------|
| UI kit | **shadcn_flutter** | Default for all UI. Read docs before coding. |
| Theme | shadcn `ThemeData` + light/dark | Dark-mode first; system themeMode |
| App shell | `ShadcnApp` / `ShadcnApp.router` | Not `MaterialApp` unless interop required |
| State | Flutter primitives first; **Riverpod** when shared/async state spans screens | YAGNI: no Riverpod for a single local `setState` |
| Routing | Navigator for 1–2 routes; **GoRouter** when multi-route / deep links | Only if in pubspec or justified |

## Docs (read before UI code)

1. `docs/UI_SPEC.md` (this file)
2. `docs/shadcn_flutter_kit.md` (condensed APIs)
3. `docs/shadcn_flutter_llms.txt` (full reference, if present)
4. `tasks/design_language.md` (approved product tokens)

**Never invent component names.** Grep/read the docs. Prefer documented APIs only.

## Style targets

- Apple HIG quality · Linear · Notion · Stripe · Airbnb
- Minimal, premium, spacious
- Neutral grayscale surfaces + **one** accent
- Default accent (if product does not specify): `#3B82F6`
- Dark mode first
- No gradients, glassmorphism, neon, skeuomorphism, purple AI-slop heroes

## Typography

- Prefer Inter / system UI font stack via theme
- Scale: display / headline / title / body / label (L·M·S)
- Hierarchy via size + weight + spacing — not random fonts

## Spacing scale (only these)

`4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`

## Radius scale (only these)

`12 · 16 · 20 · 24` (+ full pill when needed)

## Motion

- Default duration **200ms**, smooth, natural
- Use shadcn_flutter animation helpers when available
- Respect reduce-motion

## Components (defaults)

| Need | Prefer (shadcn_flutter) | Avoid |
|------|-------------------------|--------|
| App root | `ShadcnApp` | bare `MaterialApp` as final shell |
| Screen chrome | `Scaffold` + `AppBar` (shadcn) | default Material look without theme |
| Primary CTA | `Button(style: ButtonVariance.primary, …)` | raw Material `ElevatedButton` / `FilledButton` |
| Secondary | `ButtonVariance.secondary` / `outline` / `ghost` | equal-weight primary buttons |
| Destructive | `ButtonVariance.destructive` | red Material button without kit |
| Cards | `Card` | nested card stacks, heavy shadows |
| Inputs | `TextField` / Form kit | undecorated Material fields as default |
| Toggle | `Switch`, `Checkbox` | custom paint toggles |
| Nav (tabs) | `NavigationBar`, `Tabs`, `TabList` | ad-hoc bottom bars without kit |
| Feedback | `Toast`, `AlertDialog`, progress/skeleton | snackbars only as last resort |
| Lists | kit list patterns + spacing scale | dense Material defaults |

## Buttons

- Rounded, large touch targets (≥48)
- Soft hover / press (kit defaults)
- **One primary CTA per screen**

## Cards

- Rounded (12–16), thin borders, soft elevation only

## Navigation

- Modern app bars; floating/bottom nav when IA needs it
- Safe areas respected on iOS & Android

## Forms

- Filled inputs, clear labels, validation on trust boundaries

## Dialogs

- Rounded; dimmed/blurred barrier via kit overlays

## Architecture

- Feature-first folders when app grows (`lib/features/<name>/`)
- Reusable widgets in `lib/widgets/` or feature `widgets/`
- No giant god-widgets; extract when reused or >~80 lines of build UI
- No hardcoded colors/spacing — theme tokens + scales above

## Accessibility

- 48×48 min targets, WCAG AA text contrast
- No color-only meaning; scalable type
- Semantics labels on icon-only controls

## Never

- Build giant one-file screens
- Duplicate UI patterns
- Hardcode colors or spacing magic numbers outside tokens
- Mix Material widgets when a shadcn equivalent exists
- Invent APIs not in the docs
- Default Scaffold chrome without applying product theme
