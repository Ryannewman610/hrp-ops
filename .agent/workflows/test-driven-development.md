---
description: RED-GREEN-REFACTOR cycle — write test first, watch it fail, write minimal code to pass
---
# Test-Driven Development (TDD)
*Adapted from [obra/superpowers](https://github.com/obra/superpowers)*

## The Iron Law
```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```
Write code before the test? Delete it. Start over. No exceptions.

## When to Use
**Always:** New features, bug fixes, refactoring, behavior changes

**Exceptions (ask first):** Throwaway prototypes, generated code, configuration files

## Red-Green-Refactor

### 1. RED — Write Failing Test
Write one minimal test showing what should happen.

**Requirements:**
- One behavior per test
- Clear descriptive name
- Real code (no mocks unless unavoidable)

### 2. Verify RED — Watch It Fail
**MANDATORY. Never skip.**

```bash
pytest tests/path/test.py::test_name -v
```

Confirm:
- Test fails (not errors)
- Failure message is expected
- Fails because feature missing (not typos)

**Test passes?** You're testing existing behavior. Fix test.

### 3. GREEN — Minimal Code
Write simplest code to pass the test.

Don't add features, refactor other code, or "improve" beyond the test.

### 4. Verify GREEN — Watch It Pass
**MANDATORY.**

```bash
pytest tests/path/test.py::test_name -v
```

Confirm:
- Test passes
- Other tests still pass
- Output pristine (no errors, warnings)

**Test fails?** Fix code, not test.

### 5. REFACTOR — Clean Up
After green only:
- Remove duplication
- Improve names
- Extract helpers

Keep tests green. Don't add behavior.

### 6. Repeat
Next failing test for next feature.

## Good vs Bad Tests

**Good:** Clear name, tests real behavior, one thing
```python
def test_retries_failed_operations_3_times():
    attempts = 0
    # ... tests actual retry logic
```

**Bad:** Vague name, tests mock not code
```python
def test_retry_works():
    mock = Mock()
    # ... only tests mock behavior
```

## Common Rationalizations
- "Skip TDD just this once" → Stop. That's rationalization.
- "The code is too simple to test" → Simple code is the easiest to TDD.
- "I'll write tests after" → You won't. And if you do, they won't be as good.
- "I know this works" → Prove it.
