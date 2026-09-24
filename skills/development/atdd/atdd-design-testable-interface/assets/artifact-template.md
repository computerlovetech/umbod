# Testable Interface Artifact

Path: `.atdd/features/<slug>/03-testable-interface.md`

## Sections

Status | Sources | Interface Purpose | Domain Context Researched | Public Channels And Protocol Drivers (table) | Domain Specific Language (code) | Protocol Driver Interfaces (code) | Scenario To DSL Mapping (table) | Design Heuristic Check | Interface Decisions | Out Of Scope For This Interface | Open Interface Questions | Ready For Acceptance Test Writing (Yes | No)

## Design Heuristics

- Substitutability: DSL still makes sense if the SUT is replaced
- Least technical person: a domain expert can read tests against this DSL
- What not how: DSL operations free of transport, storage, and UI mechanics
- Public interfaces only: every protocol driver reaches the SUT as a real external actor would
