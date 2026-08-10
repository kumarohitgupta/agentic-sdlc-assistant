# Business Case

A short strategic framing for why this architecture matters commercially. It is written the way a delivery organization would evaluate an "adopt vs. build vs. partner" decision on agentic SDLC tooling.

## The wedge: planning and verification, not code generation

The market has crowded into AI code *generation*, where the speed gains are real but the quality bar is already well served. When AI-native delivery is benchmarked across the whole lifecycle, two things hold consistently:

- A meaningful end-to-end speed advantage over traditional delivery (on the order of 3x on well-scoped work).
- The residual quality gaps cluster in **planning and verification** — the phases this system targets — not in raw code output.

So the commercial wedge is not "write code faster." It is "**make the front and back of the lifecycle as reliable as the middle**," which is where teams currently lose time to rework.

## Where the value shows up

| Lever | Mechanism | Effect |
| --- | --- | --- |
| **Lower cost per delivery** | Task-optimized model routing — premium model only on verification | Reduced average inference cost vs. running one premium model across the chain |
| **Higher throughput** | Structured, multi-agent front-of-lifecycle | Less time from request to review-ready package |
| **Less rework** | Verification agent catches coverage gaps before build | Fewer defects traced to missed or misread requirements |
| **Governable adoption** | HITL gates at high-leverage points | Trust and auditability, which is what unblocks enterprise rollout |

## Adoption sequencing

The lower-risk path is to adopt against the **highest-confidence phases first** and expand from there. Requirements structuring and test-case generation are strong entry points: they are high-toil, relatively bounded, and easy for a human to verify. Verification-heavy and judgment-heavy steps come later, once the team trusts the earlier ones.

## Why human-in-the-loop is a feature, not a limitation

In regulated or high-stakes delivery, the blocker to AI adoption is rarely capability — it is trust and accountability. HITL gates at the three high-leverage checkpoints turn "the AI did something opaque" into "a human approved a specific, checked artifact at each phase." That auditability is often the actual precondition for adoption, which makes the gates a commercial enabler rather than a drag on speed.

## Honest limits

- This is a prototype and reference design, not a benchmarked production system; the figures above describe the *shape* of the opportunity, not a guarantee for a specific org.
- Gains depend on task scoping; ambiguous or novel work benefits less than well-bounded, repetitive delivery.
- HITL means humans stay in the critical path by design — this optimizes for trust and coverage, not full automation.
