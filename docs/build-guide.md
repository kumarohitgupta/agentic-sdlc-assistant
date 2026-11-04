# Build Guide — assemble the flow by hand in n8n

**Just want it running?** Import [`../n8n/workflow.json`](../n8n/workflow.json) instead; [`../n8n/README.md`](../n8n/README.md) takes about five minutes. This guide is for building the same flow node by hand, to understand it or to port it to another tool. Budget about an hour.

## Choose your tool

| Tool | Best for | Why |
| --- | --- | --- |
| **n8n** | Orchestration + HITL gates | Node-based workflows; form pages make the human gates obvious. The best fit for this design, and what the shipped workflow uses. |
| **Langflow** | A clear agent/LLM graph | Clean visual agent chains. |
| **Flowise** | A quick chatbot-style demo | Very fast to wire up. |

All three have a free or self-hosted tier. You'll need an API key from a provider with several model sizes, so you can route low/mid/high.

## Build steps (n8n; the shape is the same in any tool)

1. **Trigger** — a *Form Trigger* with one textarea: the feature request.
2. **Requirements Analyst** — a *Basic LLM Chain* with the prompt in [`../prompts/requirements-analyst.txt`](../prompts/requirements-analyst.txt), on your **mid** model. Fill `{{feature_request}}` from the form, and `{{feedback}}` with `(none)` on the first pass.
3. **Parse** — a *Code* node that parses the reply as JSON (strip code fences first) and checks the fields are present.
4. **Gate 1** — a *Form* page showing the requirement, with a *Decision* dropdown (Approve / Revise / Reject) and a *Feedback* box, then a *Switch* on the decision. Revise loops back to step 2 with the feedback; Reject goes to a *Form Ending* page.
5. **Story Writer** — [`../prompts/story-writer.txt`](../prompts/story-writer.txt), **low** model, then parse and **Gate 2** the same way.
6. **Test Designer** — [`../prompts/test-designer.txt`](../prompts/test-designer.txt), **mid** model, then parse.
7. **QA Verifier** — [`../prompts/qa-verifier.txt`](../prompts/qa-verifier.txt), **high** model. This produces the gap report.
8. **Conditional loop** — a *Code* node counts high-severity gaps. If there are any and fewer than 2 loops have run, route scope gaps back to step 5 (passing them as `{{feedback}}`) or test-only gaps back to step 6. Otherwise continue.
9. **Gate 3** — a final *Form* page with the tests and gap report; Approve or Reject.
10. **Output** — a *Form Ending* page that shows the assembled Delivery Spec.

To carry state through the chain, have each parse node read the previous step's state with `$('<input node>').item.json` and add its own field. The shipped workflow does exactly this; open it to compare.

## Model routing setup

In each model node, set the model explicitly:
- Analyst → mid | Story Writer → low | Test Designer → mid | QA Verifier → high

## Test it

Feed it [`../examples/sample-input-feature.md`](../examples/sample-input-feature.md) and compare with [`../examples/sample-output-delivery-spec.md`](../examples/sample-output-delivery-spec.md). Then try the cases in [`../evals/eval-cases.md`](../evals/eval-cases.md), especially the planted-gap ones (EC-4, EC-5), and record the results in [`evaluation.md`](evaluation.md).
