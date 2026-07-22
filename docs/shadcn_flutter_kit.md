# shadcn_flutter — condensed kit (Foreman)

**Source of truth for full APIs:** `docs/shadcn_flutter_llms.txt` (if present) or  
https://sunarya-thito.github.io/shadcn_flutter/llms-full.txt

Import:

```dart
import 'package:shadcn_flutter/shadcn_flutter.dart';
```

Do **not** invent names. If unsure, search the full llms file for `class <Name>`.

---

## App shell

```dart
ShadcnApp(
  title: 'App',
  theme: ThemeData(/* light */),
  darkTheme: ThemeData(/* dark */),
  themeMode: ThemeMode.system, // dark-mode first product: ThemeMode.dark
  home: const HomeScreen(),
);

// Multi-route / GoRouter:
ShadcnApp.router(
  theme: ...,
  darkTheme: ...,
  themeMode: ThemeMode.system,
  routerConfig: router, // GoRouter
);
```

Interop: kit can live beside Material temporarily; **prefer full ShadcnApp** for new Foreman apps.

---

## Screen chrome

```dart
Scaffold(
  headers: [
    AppBar(
      title: const Text('Title'),
      // trailing / leading actions via kit patterns
    ),
  ],
  child: /* body */,
  // footers / floating when needed
);
```

Use kit `Scaffold` + `AppBar` from **shadcn_flutter**, not Material defaults as the visual system.

---

## Buttons (critical)

```dart
Button(
  style: ButtonVariance.primary,
  onPressed: () {},
  child: const Text('Save'),
);

// Variants:
ButtonVariance.primary
ButtonVariance.secondary
ButtonVariance.outline
ButtonVariance.ghost
ButtonVariance.link
ButtonVariance.text
ButtonVariance.destructive
ButtonVariance.fixed
ButtonVariance.muted
ButtonVariance.card
```

One **primary** per screen. Secondary actions → secondary/outline/ghost.

---

## Card

```dart
Card(
  child: Padding(
    padding: const EdgeInsets.all(16), // spacing scale only
    child: /* content */,
  ),
);
```

Thin border + soft elevation via theme. No nested card pyramids.

---

## Inputs & forms

```dart
TextField(
  placeholder: const Text('Email'),
  onChanged: (v) {},
);

// Forms: Form, FormField, FormEntry, FormController — see full docs
Checkbox(/* ... */);
Switch(/* ... */);
Select<T>(/* ... */);
```

---

## Feedback

```dart
// Toast — see ToastLayer / show patterns in full docs
// AlertDialog for blocking confirms
AlertDialog(
  title: const Text('Delete?'),
  content: const Text('This cannot be undone.'),
  // actions: kit buttons
);
```

Skeleton / Progress for loading states (search llms file).

---

## Navigation

```dart
NavigationBar(/* destinations */);
NavigationSidebar(/* desktop */);
Tabs(/* ... */);
TabList(/* ... */);
```

Match IA from design language (tabs vs stack vs sidebar).

---

## Theme & color

- Use `ThemeData` / `Theme.of(context)` from **shadcn_flutter**
- Map product tokens from `tasks/design_language.md` into theme
- Accent default if unspecified: `#3B82F6`
- Surfaces: neutral grayscale; dark + light pairs

---

## Spacing & radius (enforce)

Spacing: 4, 8, 12, 16, 24, 32, 48, 64  
Radius: 12, 16, 20, 24

```dart
const gap = SizedBox(height: 16);
BorderRadius.circular(12);
```

---

## Motion

Prefer kit animation builders (`AnimatedValueBuilder`, etc.) when present.  
Default feel: **200ms**, ease, reduce-motion safe.

---

## Anti-hallucination checklist

Before writing UI:

1. [ ] Read `docs/UI_SPEC.md`
2. [ ] Skim this kit file
3. [ ] For any unfamiliar widget, **grep** `docs/shadcn_flutter_llms.txt`
4. [ ] Confirm constructor/params exist
5. [ ] Prefer kit over Material twin

If the package is missing: `flutter pub add shadcn_flutter` then `flutter pub get`.
