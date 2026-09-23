---
name: book-planning
description: Create detailed implementation plans when user explicitly requests. Triggers on "plan", "design", "spec out", "let's design", "create a plan" — whenever user wants structured guidance before starting work. Produces comprehensive markdown spec covering steps, architecture, risks, trade-offs, file changes, APIs, schema, dependencies, tests, success criteria, and metrics. Explores codebase first to validate assumptions. Grills user relentlessly to zero uncertainty before planning.
compatibility: Requires Explore agent for codebase search and Agent tool access to spawn an independent Haiku-model agent
---

## When to Use This Skill

Use when user explicitly says: "plan X", "design X", "spec out X", "create a plan for X", "how should we implement X", "let's design X". This skill is NOT for quick answers—it's for substantial features, refactors, migrations, or architectural changes where thorough upfront planning saves dev time.

## Workflow

### Phase 1: Grill User to Zero Uncertainty

Before exploring code or writing any plan, interview user relentlessly until you have clear answers to:

- **Problem scope**: What problem does this solve? Who benefits? What's the current state?
- **Success criteria**: How do we measure if this worked? What must be true at the end?
- **Constraints**: Timeline, performance requirements, backward-compatibility needs, compliance, scope limits?
- **Unknowns**: What are the tricky parts? Where's the user uncertain?
- **Priority**: What's most important? Any hard constraints vs nice-to-haves?
- **Context**: How does this fit into existing work? Any related projects or prior attempts?
- **Technical constraints**: Database, frameworks, infrastructure limits? Existing patterns to follow?

Don't assume—**ask until you're certain**. If user gives vague answers, drill deeper. Ask follow-ups, propose scenarios, stress-test assumptions. This usually takes 5-10 questions. Stop only when you understand the problem deeply enough to spot risks and trade-offs.

### Phase 2: Parallel Dual-Track Draft (Explore + Plan)

Run two full, independent tracks in parallel — same message, single response block:

**Track A (you, main agent):**
1. Use Explore agent (medium breadth) to understand:
   - Project structure and naming conventions
   - Relevant existing code patterns (similar features, auth patterns, data models)
   - Framework/tool versions and configuration
   - Existing similar implementations (to avoid reinventing)
   Focus on: "What exists today that's related to this task?"
2. Write your own draft plan (see Phase 3 template) from these findings.

**Track B (independent Haiku agent):** Spawn via Agent tool with `model: "haiku"`, `subagent_type: "general-purpose"` (fresh agent, not a fork — it must not see your exploration or draft plan, or its "independent opinion" is worthless). In the prompt, give it verbatim the grilled requirements from Phase 1 (problem scope, success criteria, constraints, priorities, technical constraints) and instruct it to, on its own: explore the codebase itself, then write a complete draft plan using the Phase 3 template. It must not talk to the user — it works from the requirements you hand it only.

Do not let either track see the other's output while in progress. Wait for both to finish before Phase 4.

### Phase 3: Write Comprehensive Plan

Structure the plan markdown as follows. This is the template both Track A and Track B use for their draft. Only the final, reconciled plan (Phase 4) gets saved to `specs/<task-name>.md`.

#### Template Structure

```markdown
# [Feature/Refactor Name] — Implementation Plan

## Summary
2-3 sentences: What problem does this solve? Why now?

## Success Criteria
Bulleted list of measurable outcomes. Must verify at the end:
- Metric 1 (specific target)
- Metric 2 (specific target)
- ... (3-5 criteria)

## Scope & Constraints
- In scope: [what this covers]
- Out of scope: [explicitly what it doesn't]
- Hard constraints: [immovable deadlines, performance targets, compliance]
- Trade-offs: [what we're prioritizing over what, and why]

## Architecture & Design

### High-Level Flow
Describe how the solution works end-to-end. Use ASCII diagram if helpful.

### Key Changes
- **File/module**: What changes. Why this choice over alternatives.
- **API changes**: New endpoints, signature changes, deprecations.
- **Data model**: Schema additions/changes. Migration strategy if needed.
- **Dependencies**: New packages, version upgrades, removals.

### Alternative Approaches Considered
For each major decision (tech choice, architecture pattern):
- Option A: pros/cons, why not chosen
- Option B: pros/cons, why chosen
- Option C: pros/cons, why not chosen

## Implementation Steps
Numbered sequence of steps from start to finish. Each step should be:
- Atomic (can be reviewed/tested independently if possible)
- Clear (specific files, functions, or behaviors)
- Ordered (later steps depend on earlier ones where relevant)

Example:
```
1. Add `profit_margin` column to database schema (migration)
2. Update ORM model to include new field
3. Add API endpoint `/products/:id/margins` 
4. Update frontend to fetch and display margins
5. Add unit tests for margin calculation
6. Add integration tests for full flow
7. Update documentation
```

### Risks & Mitigations
- Risk: [What could go wrong?]
  - Mitigation: [How do we prevent or recover from it?]
  - Mitigation: [Alternative approach if first fails]
- ... (3-5 major risks)

## Test Strategy
How do we verify this works?
- Unit tests: [what functions/behaviors]
- Integration tests: [what flows end-to-end]
- Manual testing: [scenarios to verify manually]
- Performance tests: [if applicable — what metrics]

## Success Checklist
At launch, verify:
- [ ] All success criteria met (with evidence)
- [ ] Tests passing (unit + integration)
- [ ] Code review approved
- [ ] Documentation updated
- [ ] Rollout plan (if needed) documented
- [ ] No regressions in related features

## Timeline & Estimates
- Phase 1 (implementation): ~X hours
- Phase 2 (testing): ~Y hours
- Phase 3 (review + polish): ~Z hours
- **Total**: ~X+Y+Z hours (rough estimate, plus buffer)

Note: Estimates are rough. Adjust based on your team's velocity.

## Open Questions
Any assumptions still uncertain? List them:
- [ ] Question 1?
- [ ] Question 2?
...

(These should be empty or near-empty after grilling—but if something remains genuinely unclear, call it out explicitly.)
```

### Phase 4: Reconcile Track A and Track B, Confirm with User

Once both drafts are done:

1. Diff the two plans section by section (scope, architecture/design decisions, implementation steps, risks, alternatives considered). Ignore wording differences — only substantive disagreements matter (different approach chosen, a risk one caught and the other missed, different step ordering, different scope boundary, etc).
2. For any difference that is a verifiable fact about the codebase (e.g. "this pattern already exists at path X" vs "it doesn't"), verify it yourself directly — grep/read the actual file — before doing anything else. Never guess, never pick a side because it "sounds more likely." If verification resolves the difference, silently take the correct side and don't bother the user with it.
3. For every remaining real disagreement that is a judgment call (not resolvable by looking at code), ask the user **one separate `AskUserQuestion` per disagreement**. Present both options neutrally — what Track A proposed and what Track B proposed — with the actual trade-off, and no recommendation unless you've verified one side is factually wrong.
4. Build the final plan using the user's choices (plus your own verified corrections from step 2). Save only this final, reconciled plan to `specs/<task-name>.md` — never save the two intermediate drafts.

## Key Principles

1. **Be specific**: Not "update auth", but "add JWT refresh-token rotation to /auth/refresh endpoint with 15-min expiry".
2. **Show trade-offs**: Explain why you chose this path over alternatives. The user should understand the reasoning, not just the decision.
3. **Flag risks early**: Better to spot problems in the plan than mid-implementation.
4. **Validate against code**: Use exploration phase to check that proposed changes align with existing patterns and won't break assumptions.
5. **Make it actionable**: Devs should be able to take the plan to implementation without major re-thinking.

## After the Plan

1. Present plan to user
2. Wait for approval, feedback, or changes
3. Revise if needed
4. Once approved: user moves to implementation (separate skill or direct coding)

Do NOT start implementing until user explicitly approves the plan.

## Example: What Good Looks Like

**Good plan** shows:
- Concrete file paths (not "update auth module", but "modify `src/auth/refresh.ts`")
- Specific API changes (endpoint URLs, request/response shapes)
- Database schema DDL or pseudo-code
- Risks that are relevant (not generic)
- Test cases tied to implementation steps
- Trade-off reasoning ("We chose approach X because Y, not approach Z because...")

**Weak plan** is vague:
- "Improve performance" without metrics
- "Refactor auth" without specifying what changes
- "Add tests" without saying which tests or why
- Risks that are too generic ("bugs might happen")
- No rationale for decisions