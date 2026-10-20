# Good and bad tests

## Good: through the real scene

Drive the game the way the player does, and check what they would see.

```gdscript
# GOOD: a real click on the button starts the fight, and the HUD shows it
func _test_pull_button_starts_the_fight() -> void:
	_click(scene.hud.pull_button_center())
	await process_frame
	expect(scene.fight.is_running(), "a click on Pull starts the fight")
	expect(scene.hud.pull_count() == 1, "the HUD counts the first pull")
```

Characteristics:

- Tests what the player or a caller cares about
- Goes through public methods and real input events
- Survives internal refactors
- The name says WHAT, not HOW
- One logical check per test

## Bad: tied to the inside

```gdscript
# BAD: calls a private helper directly, so a refactor breaks it
func _test_start() -> void:
	scene._begin_fight()
	expect(scene._state == 2, "running")
```

Red flags:

- Calling `_private` methods or reading `_private` fields
- Asserting on call counts or the order of internal calls
- The test breaks when refactoring without any change in behaviour
- The test name describes HOW, not WHAT

## Bad: tautological

The expected value is computed the way the code computes it, so the test
passes by construction.

```gdscript
# BAD: the "truth" comes from the game's own formula
var expected := Damage.after_armor(hit.amount, target.armor)
expect(target.health == target.max_health - expected, "damage applied")

# GOOD: the truth is a worked example from the spec
# (a 100 hit on 20% armor deals 80)
expect(target.health == 920, "a 100 hit on 20% armor leaves 920 of 1000")
```

Expected values come from an independent source: a worked example, a rule
written in the docs or the spec, published values (say which), or
reference fixtures.

## No mocks

Don't fake the game's own classes. Control the boundaries instead, and
list them in the project's engineering doc:

- **Time:** pause the game's clock and step it by hand.
- **Input:** synthesize input events (clicks, touches, keys).
- **Randomness:** inject a seeded random number generator.
- **Files and the network:** inject them so a test can control them.

If a new feature brings a new boundary, inject it so a test can control
it, and add it to that list.
