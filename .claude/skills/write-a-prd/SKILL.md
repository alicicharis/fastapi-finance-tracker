---
name: write-a-prd
description: Create or update PRD.md as the product roadmap. Use when user wants to write a PRD, create a product requirements document, plan a new feature, or update their product roadmap.
---

This skill creates or updates `PRD.md` at the project root as a living product roadmap. Each feature in the roadmap is detailed enough to drive a standalone spec-driven implementation pass.

**If PRD.md already exists**, read it first and update it (add/revise features, update status) rather than overwriting.

You may skip steps if you don't consider them necessary.

1. Ask the user for a detailed description of their product vision, the problems they want to solve, and any ideas for features or solutions.

2. Explore the repo to understand the current state of the codebase and what already exists.

3. Interview the user relentlessly about every aspect of the product until you reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. Focus on:
   - Overall product goals and target users
   - Feature prioritization and dependencies between features
   - Technical constraints and architectural direction

4. For each feature, sketch out the major modules that need to be built or modified. Actively look for opportunities to extract deep modules (encapsulate lots of functionality behind a simple, testable interface).

   Check with the user that the feature list, ordering, and module breakdown match their expectations.

5. Once you have a complete understanding, write or update `PRD.md` using the template below.

<prd-template>

# Product Requirements Document

## Vision

A concise statement of what this product is and who it serves.

## Problem Statement

The core problems being solved, from the user's perspective.

## Solution Overview

High-level description of the solution approach.

## User Stories

A LONG, numbered list of user stories covering the full product scope:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

## Feature Roadmap

Ordered list of features to be built. Each feature is a unit of work that can be implemented in one spec-driven development pass.

### Feature 1: <Name>

- **Status**: `planned` | `in-progress` | `done`
- **Priority**: P0 / P1 / P2
- **Depends on**: (other features, or "none")
- **Description**: What this feature does from the user's perspective.
- **Modules**: The modules to build/modify, their interfaces, and how they interact.
- **Implementation decisions**: Architectural choices, schema changes, API contracts, key interactions.
- **Testing approach**: What to test, how to test it (test external behavior, not implementation details), and prior art in the codebase.
- **Acceptance criteria**: Concrete, verifiable conditions that mean this feature is done.

### Feature 2: <Name>

(same structure)

...

## Architecture Decisions

Cross-cutting architectural decisions that apply across features:

- Technical stack choices
- Data model / schema direction
- API design patterns
- Infrastructure decisions

## Out of Scope

Things explicitly not being built.

## Open Questions

Unresolved decisions that need further input.

</prd-template>
