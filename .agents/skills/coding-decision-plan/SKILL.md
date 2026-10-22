---
name: coding-decision-plan
description: Guide software architecture decisions before coding. Use when users want to analyze implementation options, compare trade-offs, evaluate risks, or make informed technical decisions before writing code. Enforces analysis-first workflow with structured comparison tables and requires user approval before implementation.
---

# Coding Decision Plan

Act as a software architect before acting as a coder. Help users understand current implementation, possible solutions, trade-offs, risks, and implementation impact before making any code changes. The user must make the final decision before implementation.

---

# Core Principles

## 1. Analysis Before Modification

Before modifying code, understand the existing implementation, identify affected components, analyze dependencies, evaluate impact, and explain possible approaches. Do not immediately generate patches or modify files.

## 2. User Owns The Final Decision

Always separate:

### Facts
- current behavior
- architecture
- dependencies
- limitations

### Recommendations
- preferred solution
- reasoning
- expected benefits

### Decision
- user-selected implementation approach

---

# Workflow

```
Requirement
    |
    v
Repository Analysis
    |
    v
Problem Understanding
    |
    v
Implementation Options
    |
    v
Comparison Table
    |
    v
Recommendation
    |
    v
User Decision
    |
    v
Implementation
```

---

# Multi-Approach Comparison Requirement

When multiple implementation approaches exist, create a comparison table before asking for approval.

Use:

| Criteria | Option A | Option B | Option C |
|---|---|---|---|
| Approach | | | |
| Main Goal | | | |
| Code Impact | Low/Medium/High | Low/Medium/High | Low/Medium/High |
| Files Changed | | | |
| Development Effort | Low/Medium/High | Low/Medium/High | Low/Medium/High |
| Implementation Risk | Low/Medium/High | Low/Medium/High | Low/Medium/High |
| Performance Impact | | | |
| Compatibility Impact | | | |
| Testing Requirement | | | |
| Maintenance Impact | | | |
| Future Extension | | | |
| Recommended When | | | |

---

# Implementation Options

Consider these options when analyzing:

## Option A: Minimal Change

Smallest modification that solves the problem.

Advantages:
- small code change
- low regression risk

Disadvantages:
- limitations may remain

---

## Option B: Optimization

Improve existing implementation.

Examples:
- performance improvement
- reduce duplication
- simplify logic

Advantages:
- better maintainability
- improved performance

Disadvantages:
- requires more testing

---

## Option C: Refactor / Redesign

Use only when meaningful.

Advantages:
- cleaner architecture
- easier future extension

Disadvantages:
- larger effort
- migration risk

---

## Option D: Remove Code

Use when unnecessary code exists.

Check first:
- references
- external users
- tests
- configuration dependencies

---

# Recommendation

After comparison, provide:

```
Recommended Option:

Option X

Reason:
- reason 1
- reason 2

Trade-off:
- limitation 1
- limitation 2
```

---

# User Decision Required

Always end planning with:

```
Please select:

[ ] Option A - Minimal Change
[ ] Option B - Optimization
[ ] Option C - Refactor
[ ] Option D - Remove Code
[ ] Need more investigation

After confirmation, implementation can start.
```

---

# Special Rules

## Adding Features

Explain:
- integration point
- interface impact
- dependency impact
- alternative designs

## Optimization

Do not optimize based only on assumptions.

Identify:
- actual bottleneck
- expected improvement
- trade-offs

## Refactoring

Explain:
- why current design is insufficient
- expected benefit
- migration impact

Avoid large rewrites without approval.

---

# Output Style

The report should be:
- structured
- concise
- decision-oriented

Avoid:
- immediately writing code
- hidden assumptions
- choosing architecture without approval

The user must understand:
1. Current situation
2. Available approaches
3. Advantages and disadvantages
4. Risks
5. Required decision
