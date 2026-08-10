# Build Guide — assemble the working flow (no coding)

This walks you through building the actual, runnable pipeline in a visual agent-orchestration tool. No code. Budget about an hour for a first pass.

## Choose your tool

Any of these three can build the whole thing. Pick based on what you want the screenshots to show:

| Tool | Best for | Why |
| --- | --- | --- |
| **n8n** | Showing orchestration + HITL gates | Node-based workflows; native "Wait / approval" steps make the human gates visually obvious. Strongest fit for *this* project's story. |
| **Langflow** | Showing agent/LLM graph clearly | Clean visual agent chains; screenshots read as "agent design." |
| **Flowise** | Fastest to a working chatbot-style demo | Very quick to wire up; good if you want a talk-to-it demo. |

**Recommendation:** start with **n8n** — the approval gates are the distinctive part of this design, and n8n makes them the most visible. Langflow is a fine alternative if you prefer a cleaner agent-graph screenshot.

All three have a free/self-host tier. You'll also need an API key from one LLM provider that offers multiple model sizes, so you can demonstrate the low/mid/high routing.

## Build steps (n8n framing; the shape is the same in any tool)

1. **Trigger** — a manual/form trigger that takes one text field: the feature request.
2. **Node: Requirements Analyst** — an LLM node using the prompt in [`../prompts/requirements-analyst.txt`](../prompts/requirements-analyst.txt). Assign your **mid** model. Output parsed into the `requirement` object.
3. **Gate 1** — an approval/wait step: show the requirement, wait for a human "approve" before continuing. (In n8n, a Wait node + a simple form; in Langflow/Flowise, a manual review checkpoint.)
4. **Node: Story Writer** — prompt from [`../prompts/story-writer.txt`](../prompts/story-writer.txt). Assign your **low** model.
5. **Gate 2** — approval/wait step on the stories.
6. **Node: Test Designer** — prompt from [`../prompts/test-designer.txt`](../prompts/test-designer.txt). Assign your **low–mid** model.
7. **Node: QA Verifier** — prompt from [`../prompts/qa-verifier.txt`](../prompts/qa-verifier.txt). Assign your **high** model. This produces the gap report.
8. **Conditional loop** — if the gap report contains any `high` severity item, route back to step 4 with the gap report attached. Cap at 2 loops.
9. **Gate 3** — final approval/wait: human reviews the checked package and approves.
10. **Output** — assemble the full Delivery Spec and return/download it.

## Model routing setup

The point of the project is visible in this step. In each LLM node, set the model explicitly:
- Analyst → mid | Story Writer → low | Test Designer → low–mid | QA Verifier → high

Take a screenshot of the workflow showing different models on different nodes — that image *is* the "task-optimized routing" evidence for your portfolio.

## Test it

Feed it [`../examples/sample-input-feature.md`](../examples/sample-input-feature.md). Compare the result to [`../examples/sample-output-delivery-spec.md`](../examples/sample-output-delivery-spec.md). Then run the cases in [`../evals/eval-cases.md`](../evals/eval-cases.md), including the planted-gap ones, and fill in the results table in [`evaluation.md`](evaluation.md).

## What to capture for the repo

- A screenshot of the full workflow → save to `assets/`.
- A screenshot showing the different model tiers per node.
- One completed Delivery Spec from a real run → `examples/`.
- Your filled-in evaluation results table.

Those four artifacts turn "I designed a pipeline" into "I built and measured one."
