---
description: 4-phase root cause debugging process — ALWAYS find root cause before attempting fixes
---
# Systematic Debugging
*Adapted from [obra/superpowers](https://github.com/obra/superpowers)*

## The Iron Law
```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```
If you haven't completed Phase 1, you cannot propose fixes.

## When to Use
Use for ANY technical issue: test failures, bugs, unexpected behavior, performance problems, build failures, integration issues.

**Use ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work

## The Four Phases

### Phase 1: Root Cause Investigation
**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully** — Don't skip past errors/warnings. Read stack traces completely. Note line numbers, file paths, error codes.
2. **Reproduce Consistently** — Can you trigger it reliably? Exact steps? Every time?
3. **Check Recent Changes** — Git diff, recent commits, new dependencies, config changes
4. **Gather Evidence** — In multi-component systems, add diagnostic logging at each boundary to find WHERE it breaks
5. **Trace Data Flow** — Where does bad value originate? Keep tracing up until you find the source. Fix at source, not symptom.

### Phase 2: Pattern Analysis
1. **Find Working Examples** — Locate similar working code in same codebase
2. **Compare Against References** — Read reference implementations COMPLETELY
3. **Identify Differences** — List every difference between working and broken, however small
4. **Understand Dependencies** — What components, settings, config, environment?

### Phase 3: Hypothesis and Testing
1. **Form Single Hypothesis** — "I think X is the root cause because Y"
2. **Test Minimally** — SMALLEST possible change. One variable at a time.
3. **Verify** — Did it work? Yes → Phase 4. No → NEW hypothesis.
4. **When You Don't Know** — Say so. Don't pretend. Ask for help.

### Phase 4: Implementation
1. **Create Failing Test Case** — Simplest possible reproduction, automated if possible
2. **Implement Single Fix** — ONE change at a time. No "while I'm here" improvements.
3. **Verify Fix** — Test passes? No regressions? Issue actually resolved?
4. **If 3+ Fixes Failed** — STOP. Question architecture. Discuss before continuing.

## Red Flags — STOP and Follow Process
- "Let me try..." without investigating root cause
- Changing multiple things at once
- "While I'm in here..." scope creep
- Fixing symptoms instead of causes
- Ignoring error messages
- Not reading the full error/stack trace
