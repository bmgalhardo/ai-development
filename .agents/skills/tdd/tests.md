# Good and bad tests

The examples are in Python. The rules hold in any language; the project's
engineering doc says how its own tests are written.

## Good: through the public interface

Drive the code the way its user or caller does, and check what they would
see.

```python
# GOOD: loading a file through the pipeline's entry point, checking the result
def test_rows_with_a_missing_id_are_rejected():
    result = pipeline.ingest(fixture("orders_with_gaps.csv"))
    assert result.accepted == 8
    assert result.rejected == [Rejection(line=4, reason="missing order id")]
```

For a program with a UI, the same holds: send a real click or key, then
check what is shown.

Characteristics:

- Tests what the user or a caller cares about
- Goes through public functions and real input
- Survives internal refactors
- The name says WHAT, not HOW
- One logical check per test

## Bad: tied to the inside

```python
# BAD: calls a private helper directly, so a refactor breaks it
def test_validate():
    assert pipeline._check_row({"id": None})._state == 2
```

Red flags:

- Calling `_private` functions or reading `_private` fields
- Asserting on call counts or the order of internal calls
- The test breaks when refactoring without any change in behaviour
- The test name describes HOW, not WHAT

## Bad: tautological

The expected value is computed the way the code computes it, so the test
passes by construction.

```python
# BAD: the "truth" comes from the code's own formula
expected = pricing.after_discount(order.total, customer.discount)
assert invoice.amount == expected

# GOOD: the truth is a worked example from the spec
# (a 100 order with a 20% discount costs 80)
assert invoice.amount == 80
```

Expected values come from an independent source: a worked example, a rule
written in the docs or the spec, published values (say which), or
reference fixtures.

## No mocks

Don't fake the project's own classes. Control the boundaries instead, and
list them in the project's engineering doc:

- **Time:** inject the clock and step it by hand.
- **Input:** synthesize input (requests, files, clicks, keys).
- **Randomness:** inject a seeded random number generator.
- **Files, the network and services:** inject them so a test can control
  them.

If a new feature brings a new boundary, inject it so a test can control
it, and add it to that list.
