# Agent: Secretary

## Role
Reads the goal, writes the plan, dispatches to Logistics and Financial. Turns exceptions into tasks. Reports to the front end. Drafts chase emails.

## Build Priority: STUB EARLY, DEEPEN LAST

The visible plan is what judges watch. A rough version must exist in the first hour.

## Responsibilities

### P0
- [ ] Read the goal, write the plan, dispatch to the other two
- [ ] Push the plan and status to the front end

### P1
- [ ] Exceptions → task list
- [ ] Final report — cash in and out, categories, top 3 actions

### P2
- [ ] Draft the chase emails for approval

## Dispatch Flow
1. Receive goal from user (e.g., "Close out September")
2. Write plan: what Logistics will do, what Financial will do, in what order
3. Push plan to frontend (plan panel)
4. Dispatch to Logistics → collect documents
5. Dispatch to Financial → build ledger, validate, raise exceptions
6. Receive exceptions from Financial
7. Convert exceptions to tasks (task list on frontend)
8. Draft chase emails for low-confidence / overdue items
9. Final report: cash in, cash out, categories, top 3 actions

## Idle Protocol
If stub is complete and Financial needs help, pivot to Financial support.
