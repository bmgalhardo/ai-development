# Coding standards

How code in the game projects should be written. Based on Robert C.
Martin's *Clean Code* and SOLID, applied to Godot 4 and GDScript. The code
review reads this file; each rule is a judgement call unless it says
otherwise. A project's own rules, in its `AGENTS.md`, win over anything
here; a project can keep its own `CODING_STANDARDS.md` instead.

## How Clean Code maps onto Godot

- **A script is a class.** Each `.gd` file is one class; give a reusable
  one a `class_name`. A script attached to a node is that node's class.
- **A node is a module.** Split behaviour into child nodes with their own
  scripts, and compose them in the scene, rather than growing one script.
  Prefer composition to `extends` chains.
- **Signals up, calls down.** A parent calls its children's methods; a
  child tells its parent by emitting a signal. A child never reaches up
  (`get_parent()`, `owner`, `../`) or across into a sibling.
- **Data as plain resources or constants.** Tables such as levels, enemies
  and abilities are data that the code reads, so adding a level, an enemy
  or an ability is a data change, not a code change.

## Classes and modules

- **One reason to change.** A script does one job: drawing the HUD,
  running the game clock, laying out a menu. If you describe it with
  "and", split it.
- **Small classes.** About 300 lines is a warning sign. Put new
  behaviour in its own script; when you touch a large script, pulling one
  responsibility out into its own node is welcome.
- **Open for extension.** Add a new kind of thing (a level, an enemy, an
  ability) through data or a new script, without editing a chain of `if`s in
  several places.
- **Depend on the narrow surface.** Call a node through a few public
  methods. Don't reach into its fields from outside: no `inventory.items[...] =`,
  no `inventory.slot = 0`; give the node a method (`inventory.reset()`).
- **No parallel arrays.** Keep values that belong together in one record
  (a dictionary with named keys, an inner class or a resource), not in two
  lists kept in the same order.

## Functions

- **Short.** A function does one thing at one level of abstraction. Aim
  for under about 20 lines.
  - `_draw()`, `_process()` and `_input()` read as a list of calls to
    named helpers (`_draw_dial()`, `_draw_band()`), not as one long body.
- **Few arguments.** Three or fewer. Pass a small record instead of a long
  list.
- **No flag arguments.** A `bool` that switches what a function does
  means two functions.
- **No hidden state.** Don't use a timer value or a magic number as a
  state flag; name the state (an enum or a boolean field).
- **Command or query.** A function either changes something or returns
  something, not both. Validating code doesn't mutate what it checks.

## Names

- **Reveal intent.** A name says what a thing is or does: `room_open(room)`,
  not `check(r)`.
  - Avoid `data`, `extra`, `info`, `tmp` and single letters, except loop
    indices and maths.
  - Rename when the meaning changes: `enemy_rect` becomes `row_rect` once it
    serves every list.
- **The game's words.** Use the project's glossary (its domain doc says
  where) in code too.
- **Godot style** (mechanical): `snake_case` for functions and variables,
  `PascalCase` for classes and nodes, `CONSTANT_CASE` for constants,
  signals in the past tense (`room_chosen`), and booleans read as yes or
  no questions (`is_open`, `has_book`).

## Constants and duplication

- **Name every number that means something:** sizes, colours, alphas,
  timings. Drawing code is the worst offender.
- **One source.** A palette colour, a lookup (such as a team's colour) or a layout measurement lives in one place. Drawing and hit
  testing share the same rect.
- **Tools that read GDScript** (regex over a constant) fail with a clear
  message when they can't find it, and say so in their docstring.

## Types and errors

- **Typed GDScript.** Give variables, parameters and return values static
  types, and use typed arrays (`Array[Rect2]`) where they fit.
- **Fail loudly.** Use `assert` or `push_error` for a broken invariant;
  don't silently return a default that hides a bug.

## Comments

- **Explain why, not what.** If a comment explains what code does, rename
  or extract until it doesn't need to.
- **`##` doc comments** on a class and its public functions, directly
  above the declaration they document.
- **No history.** Don't write "v80", "before version 80" or "the old
  way" in code or docs; git keeps history. Say what is true now.
- **Keep comments true.** A comment that no longer matches the code is
  a bug.

## Tests

- **Through the seams.** Tests drive the game as a player would (real
  input events on the real scene) and check what the player sees.
- **Read freely, write through the front door.** A test may read a node's
  state to assert on it, but sets up state through the game's own calls.
- **One behaviour per test function,** named for that behaviour. Tests are
  fast, independent and repeatable.
- **Literal expectations.** Expected values are written out ("20 Sep
  2012"), not computed by the code under test.
