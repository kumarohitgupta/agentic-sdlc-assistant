# Running it in n8n

`workflow.json` is the whole pipeline as an importable n8n workflow: a form to submit a feature request, the four Claude agents, and three approval gates that appear as pages of the same form. Tested on n8n 2.46 (self-hosted). n8n Cloud is always current; on an older self-hosted n8n, some nodes may import as unknown — update n8n if that happens.

## Setup (about 5 minutes)

1. **Import.** In n8n, open **Workflows → Create → ⋯ → Import from file** and pick `workflow.json`. (Or copy the file's contents and paste onto an empty canvas.)
2. **Add your Claude key.** Open the node **Claude Sonnet · analyst**. Under *Credential*, choose **Create new credential**, paste your Anthropic API key (from <https://platform.claude.com>), and save. Then open the other three model nodes (**Claude Haiku · story writer**, **Claude Sonnet · test designer**, **Claude Opus · QA verifier**) and select the same credential.
3. **Save** the workflow.

## Run it

- **From the editor:** click **Test workflow** (*Execute workflow* in some versions). The form opens in a new tab.
- **As a shareable link:** **Publish** (or toggle **Active**) and open `https://<your-n8n>/form/sdlc-assistant`. Anyone with the link can use it, and each run spends from your API key, so set **Authentication** on the *Feature request form* node (Basic Auth) before sharing widely.

Then:

1. Describe the feature and press **Start**.
2. **Gate 1:** the requirement is shown with its open questions. Choose **Approve**, **Revise** (type your answers or changes in *Feedback*), or **Reject**.
3. **Gate 2:** the user stories. Same choices.
4. Tests are written and checked. If the QA Verifier finds high-severity gaps, the workflow loops back on its own (at most twice). Scope gaps return to the Story Writer, so you may see Gate 2 again with revised stories. Test gaps return to the Test Designer.
5. **Gate 3:** final sign-off, with the QA gap report, the coverage check, the stories and the tests.
6. The last page shows the full Delivery Spec with its JSON. The same data is in the n8n execution log (**Executions** tab → the run → *Assemble Delivery Spec*).

A run with Claude typically takes 2–4 minutes, mostly in the Test Designer and QA Verifier steps. The form shows a waiting screen between gates.

## Changing it

- **Re-route a model:** open any model node and change *Model*, for example to put the QA Verifier on Sonnet and compare.
- **Change a prompt:** edit the file in [`../prompts/`](../prompts/), then run `python n8n/build_workflow.py` to regenerate `workflow.json`, so the Python runner and n8n stay identical. Editing a prompt directly in n8n works too, but it won't flow back to the repo.
- **Loop cap:** `MAX_LOOPS` at the top of the *Check gaps & route* code node.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "Credentials not set" / node shows a red warning | Step 2: each of the four model nodes needs the credential selected. |
| `model not found` | Your account may not have that model id. Open the model node and pick another from the list. |
| "...returned output that is not usable" | The model reply wasn't valid JSON even after tolerant parsing. Re-run; if it repeats, raise *Maximum Number of Tokens* on that model node. |
| Form link returns 404 | The workflow isn't published/active, or another copy of it already uses the path `sdlc-assistant`. Deactivate the other copy, or change *Form Path* under the trigger's options. |
| Waiting screen never ends | Check **Executions**: the run will show which node failed and why. |
