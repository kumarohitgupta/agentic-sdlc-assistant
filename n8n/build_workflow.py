"""Build n8n/workflow.json from prompts/*.txt.

The prompts are the single source of truth for both runtimes. Edit a prompt,
then run:

    python n8n/build_workflow.py          # write n8n/workflow.json
    python n8n/build_workflow.py --check  # fail if workflow.json is out of date (CI)

Tested on n8n 2.46 (Form Trigger 2.3, Form 2.3, Basic LLM Chain 1.9,
Anthropic Chat Model 1.6, Switch 3.2, Code 2).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "workflow.json"

sys.path.insert(0, str(ROOT))
from sdlc_assistant.config import AGENT_TIERS, MAX_TOKENS, TIER_MODELS  # noqa: E402

MAX_LOOPS = 2

# ---------------------------------------------------------------- helpers

_ids: dict[str, str] = {}


def node_id(name: str) -> str:
    # Stable ids so regenerating doesn't churn the diff.
    if name not in _ids:
        _ids[name] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentic-sdlc-assistant/{name}"))
    return _ids[name]


def prompt_expression(filename: str) -> str:
    """Turn {{placeholder}} prompt text into an n8n expression."""
    text = (ROOT / "prompts" / filename).read_text(encoding="utf-8")
    subs = {
        "feature_request": "{{ $json.feature_request }}",
        "feedback": "{{ $json.feedback }}",
        "requirement": "{{ JSON.stringify($json.requirement, null, 2) }}",
        "stories": "{{ JSON.stringify($json.stories, null, 2) }}",
        "tests": "{{ JSON.stringify($json.tests, null, 2) }}",
    }
    for key, expr in subs.items():
        text = text.replace("{{" + key + "}}", expr)
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        raise SystemExit(f"{filename}: unknown placeholders {leftover}")
    return "=" + text


# Shared JavaScript, prepended to every Code node that needs it.
JS_LIB = r"""
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const list = (items) => (items && items.length) ? '<ul>' + items.map((i) => '<li>' + esc(i) + '</li>').join('') + '</ul>' : '<p><i>(none)</i></p>';
const noTripleQuotes = (s) => String(s ?? '').split('\"\"\"').join("'''");

function extractJson(text) {
  let t = String(text ?? '').trim();
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) t = fence[1].trim();
  try { return JSON.parse(t); } catch (e) { /* fall through */ }
  const starts = [t.indexOf('{'), t.indexOf('[')].filter((i) => i !== -1);
  if (!starts.length) throw new Error('no JSON found in the model reply');
  const start = Math.min(...starts);
  const end = t.lastIndexOf(t[start] === '{' ? '}' : ']');
  return JSON.parse(t.slice(start, end + 1));
}

function fail(agent, msg, text) {
  throw new Error(agent + ' returned output that is not usable (' + msg + '). Re-run the step, or check the model. Reply started: ' + String(text ?? '').slice(0, 300));
}

function checkRequirement(d) {
  if (!d || typeof d !== 'object' || Array.isArray(d)) return 'expected a JSON object';
  if (!d.problem) return '"problem" is missing';
  for (const k of ['in_scope', 'out_of_scope', 'assumptions', 'open_questions']) if (!Array.isArray(d[k])) return '"' + k + '" must be a list';
  if (!d.in_scope.length) return '"in_scope" is empty';
  return null;
}

function checkStories(d) {
  if (!Array.isArray(d) || !d.length) return 'expected a non-empty array of stories';
  const seen = new Set();
  for (const s of d) {
    if (!s.id || !s.story || !Array.isArray(s.acceptance_criteria) || !s.acceptance_criteria.length) return 'each story needs id, story and acceptance_criteria';
    s.acceptance_criteria = s.acceptance_criteria.map((ac, i) => typeof ac === 'string' ? { id: s.id + '.AC' + (i + 1), criterion: ac } : ac);
    for (const ac of s.acceptance_criteria) {
      if (!ac.id || !ac.criterion) return s.id + ': each criterion needs id and criterion';
      if (seen.has(ac.id)) return 'duplicate criterion id ' + ac.id;
      seen.add(ac.id);
    }
  }
  return null;
}

function checkTests(d) {
  if (!Array.isArray(d) || !d.length) return 'expected a non-empty array of tests';
  for (const t of d) {
    if (!t.id || !t.criterion_id || !t.case) return 'each test needs id, criterion_id and case';
    if (!['positive', 'negative', 'edge'].includes(t.type)) return t.id + ': type must be positive, negative or edge';
  }
  return null;
}

function checkGaps(d) {
  if (!Array.isArray(d)) return 'expected an array (use [] for no gaps)';
  for (const g of d) {
    if (!g.type || !g.severity || !g.detail) return 'each gap needs type, severity and detail';
    g.severity = String(g.severity).toLowerCase();
    if (!['high', 'medium', 'low'].includes(g.severity)) return 'severity must be high, medium or low';
    g.refs = g.refs || [];
  }
  return null;
}

function coverage(stories, tests) {
  const kinds = {};
  for (const s of stories) for (const ac of s.acceptance_criteria) kinds[ac.id] = new Set();
  const unknown = [];
  for (const t of tests) { if (kinds[t.criterion_id]) kinds[t.criterion_id].add(t.type); else unknown.push(t.id); }
  const missing = {};
  for (const [id, set] of Object.entries(kinds)) {
    const lack = ['positive', 'negative', 'edge'].filter((k) => !set.has(k));
    if (lack.length) missing[id] = lack;
  }
  const criteria = Object.keys(kinds).length;
  return { criteria, fully_covered: criteria - Object.keys(missing).length, missing, tests_with_unknown_criterion: unknown };
}

function requirementHtml(r) {
  return '<p><b>Problem:</b> ' + esc(r.problem) + '</p>' +
    '<p><b>In scope</b></p>' + list(r.in_scope) + '<p><b>Out of scope</b></p>' + list(r.out_of_scope) +
    '<p><b>Assumptions</b></p>' + list(r.assumptions) + '<p><b>Open questions</b> (answer these in Feedback and choose Revise)</p>' + list(r.open_questions);
}

function storiesHtml(stories) {
  return stories.map((s) => '<p><b>' + esc(s.id) + '</b> ' + esc(s.story) + '</p><ul>' +
    s.acceptance_criteria.map((ac) => '<li><code>' + esc(ac.id) + '</code> ' + esc(ac.criterion) + '</li>').join('') + '</ul>').join('');
}

function testsHtml(tests) {
  return '<ul>' + tests.map((t) => '<li><b>' + esc(t.id) + '</b> · ' + esc(t.criterion_id) + ' · <i>' + esc(t.type) + '</i> — ' + esc(t.case) + '</li>').join('') + '</ul>';
}

function gapsHtml(gaps) {
  if (!gaps.length) return '<p>No gaps found.</p>';
  const order = { high: 0, medium: 1, low: 2 };
  return '<ul>' + [...gaps].sort((a, b) => order[a.severity] - order[b.severity]).map((g) =>
    '<li><b>' + esc(g.severity.toUpperCase()) + '</b> · ' + esc(g.type) + (g.refs.length ? ' (' + esc(g.refs.join(', ')) + ')' : '') + ': ' + esc(g.detail) + '</li>').join('') + '</ul>';
}

function coverageHtml(c) {
  let h = '<p>' + c.fully_covered + ' of ' + c.criteria + ' acceptance criteria have positive, negative and edge tests.</p>';
  const miss = Object.entries(c.missing);
  if (miss.length) h += '<ul>' + miss.map(([id, k]) => '<li><code>' + esc(id) + '</code> missing: ' + esc(k.join(', ')) + '</li>').join('') + '</ul>';
  if (c.tests_with_unknown_criterion.length) h += '<p>Tests pointing at an unknown criterion: ' + esc(c.tests_with_unknown_criterion.join(', ')) + '</p>';
  return h;
}
"""


def code_node(name: str, body: str, pos: tuple[int, int], lib: bool = True) -> dict:
    js = (JS_LIB.strip() + "\n\n" if lib else "") + body.strip() + "\n"
    return {
        "parameters": {"mode": "runOnceForEachItem", "jsCode": js},
        "id": node_id(name), "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": list(pos),
    }


def chain_node(name: str, prompt_file: str, pos: tuple[int, int]) -> dict:
    return {
        "parameters": {"promptType": "define", "text": prompt_expression(prompt_file), "batching": {}},
        "id": node_id(name), "name": name, "type": "@n8n/n8n-nodes-langchain.chainLlm", "typeVersion": 1.9,
        "position": list(pos),
    }


def model_node(name: str, agent: str, pos: tuple[int, int]) -> dict:
    model = TIER_MODELS[AGENT_TIERS[agent]]
    return {
        "parameters": {
            "model": {"__rl": True, "mode": "id", "value": model},
            "options": {"maxTokensToSample": MAX_TOKENS[agent], "temperature": 0.2},
        },
        "id": node_id(name), "name": name, "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic", "typeVersion": 1.6,
        "position": list(pos),
    }


def gate_node(name: str, title: str, description: str, html_expr: str, choices: list[str],
              pos: tuple[int, int], feedback: bool = True) -> dict:
    fields = [
        {"fieldType": "html", "elementName": "artifact", "html": html_expr},
        {"fieldLabel": "Decision", "fieldType": "dropdown", "requiredField": True,
         "fieldOptions": {"values": [{"option": c} for c in choices]}},
    ]
    if feedback:
        fields.append({"fieldLabel": "Feedback", "fieldType": "textarea",
                       "placeholder": "Required for Revise: what should change? Answers to open questions go here."})
    return {
        "parameters": {
            "formFields": {"values": fields},
            "options": {"formTitle": title, "formDescription": description, "buttonLabel": "Continue"},
        },
        "id": node_id(name), "name": name, "type": "n8n-nodes-base.form", "typeVersion": 2.3,
        "position": list(pos), "webhookId": node_id(name + "/webhook"),
    }


def switch_node(name: str, expr: str, outputs: int, pos: tuple[int, int]) -> dict:
    return {
        "parameters": {"mode": "expression", "numberOutputs": outputs, "output": expr},
        "id": node_id(name), "name": name, "type": "n8n-nodes-base.switch", "typeVersion": 3.2,
        "position": list(pos),
    }


def ending_node(name: str, title: str, text_expr: str, pos: tuple[int, int]) -> dict:
    return {
        "parameters": {"operation": "completion", "respondWith": "showText", "responseText": text_expr},
        "id": node_id(name), "name": name, "type": "n8n-nodes-base.form", "typeVersion": 2.3,
        "position": list(pos), "webhookId": node_id(name + "/webhook"),
    }


# ---------------------------------------------------------------- the workflow

def build() -> dict:
    N = []  # nodes
    C: dict[str, dict] = {}  # connections

    def link(src: str, dst: str, out: int = 0, kind: str = "main"):
        outs = C.setdefault(src, {}).setdefault(kind, [])
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": dst, "type": kind, "index": 0})

    def use_model(model: str, chain: str):
        link(model, chain, kind="ai_languageModel")

    N.append({
        "parameters": {
            "formTitle": "Agentic SDLC Delivery Assistant",
            "formDescription": "Describe a feature in a few sentences. Four Claude agents turn it into requirements, "
                               "user stories, tests and a QA gap report. You approve each phase on the next pages.",
            "formFields": {"values": [{
                "fieldLabel": "Feature request", "fieldType": "textarea", "requiredField": True,
                "placeholder": "e.g. Employees request time off; their manager approves or rejects; "
                               "approved time shows on the team calendar.",
            }]},
            "options": {"buttonLabel": "Start", "path": "sdlc-assistant"},
        },
        "id": node_id("Feature request form"), "name": "Feature request form",
        "type": "n8n-nodes-base.formTrigger", "typeVersion": 2.3, "position": [0, 300],
        "webhookId": node_id("Feature request form/webhook"),
    })

    N.append(code_node("Start run", """
return { json: {
  feature_request: noTripleQuotes($json['Feature request']).trim(),
  feedback: '(none)',
  next_test_feedback: '(none)',
  loops: 0,
} };
""", (220, 300)))
    link("Feature request form", "Start run")

    # ---- Phase 1: requirement + Gate 1
    N.append(code_node("Analyst input", "return { json: $json };", (440, 300), lib=False))
    N.append(chain_node("Requirements Analyst", "requirements-analyst.txt", (660, 300)))
    N.append(model_node("Claude Sonnet · analyst", "requirements_analyst", (660, 520)))
    N.append(code_node("Check requirement", """
const state = { ...$('Analyst input').item.json };
let data;
try { data = extractJson($json.text); } catch (e) { fail('Requirements Analyst', e.message, $json.text); }
const problem = checkRequirement(data);
if (problem) fail('Requirements Analyst', problem, $json.text);
state.requirement = data;
state.view = requirementHtml(data);
return { json: state };
""", (880, 300)))
    N.append(gate_node("Gate 1 · requirement", "Gate 1 of 3 — approve the requirement",
                       "Approve to move on, Revise to have the analyst redraft using your feedback, or Reject to stop.",
                       "={{ $json.view }}", ["Approve", "Revise", "Reject"], (1100, 300)))
    N.append(switch_node("Gate 1 decision", "={{ ['Approve', 'Revise', 'Reject'].indexOf($json.Decision) }}", 3, (1320, 300)))
    N.append(code_node("Requirement approved", """
const state = { ...$('Check requirement').item.json };
delete state.view;
state.feedback = '(none)';
return { json: state };
""", (1540, 200), lib=False))
    N.append(code_node("Redraft requirement", """
const state = { ...$('Check requirement').item.json };
delete state.view;
state.feedback = noTripleQuotes($json.Feedback || '(The reviewer asked for a redraft without details: re-check the request and tighten the open questions.)');
return { json: state };
""", (1540, 420)))
    link("Start run", "Analyst input")
    link("Analyst input", "Requirements Analyst")
    use_model("Claude Sonnet · analyst", "Requirements Analyst")
    link("Requirements Analyst", "Check requirement")
    link("Check requirement", "Gate 1 · requirement")
    link("Gate 1 · requirement", "Gate 1 decision")
    link("Gate 1 decision", "Requirement approved", 0)
    link("Gate 1 decision", "Redraft requirement", 1)
    link("Gate 1 decision", "Rejected", 2)
    link("Redraft requirement", "Analyst input")

    # ---- Phase 2: stories + Gate 2
    N.append(code_node("Story input", "return { json: $json };", (1760, 200), lib=False))
    N.append(chain_node("Story Writer", "story-writer.txt", (1980, 200)))
    N.append(model_node("Claude Haiku · story writer", "story_writer", (1980, 420)))
    N.append(code_node("Check stories", """
const state = { ...$('Story input').item.json };
let data;
try { data = extractJson($json.text); } catch (e) { fail('Story Writer', e.message, $json.text); }
const problem = checkStories(data);
if (problem) fail('Story Writer', problem, $json.text);
state.stories = data;
state.view = storiesHtml(data);
return { json: state };
""", (2200, 200)))
    N.append(gate_node("Gate 2 · stories", "Gate 2 of 3 — approve the user stories",
                       "Approve to generate tests, Revise to have the story writer redraft using your feedback, or Reject to stop.",
                       "={{ $json.view }}", ["Approve", "Revise", "Reject"], (2420, 200)))
    N.append(switch_node("Gate 2 decision", "={{ ['Approve', 'Revise', 'Reject'].indexOf($json.Decision) }}", 3, (2640, 200)))
    N.append(code_node("Stories approved", """
const state = { ...$('Check stories').item.json };
delete state.view;
state.feedback = state.next_test_feedback || '(none)';
state.next_test_feedback = '(none)';
return { json: state };
""", (2860, 100), lib=False))
    N.append(code_node("Redraft stories", """
const state = { ...$('Check stories').item.json };
delete state.view;
state.feedback = noTripleQuotes($json.Feedback || '(The reviewer asked for a redraft without details: re-check coverage of in_scope.)');
return { json: state };
""", (2860, 320)))
    link("Requirement approved", "Story input")
    link("Story input", "Story Writer")
    use_model("Claude Haiku · story writer", "Story Writer")
    link("Story Writer", "Check stories")
    link("Check stories", "Gate 2 · stories")
    link("Gate 2 · stories", "Gate 2 decision")
    link("Gate 2 decision", "Stories approved", 0)
    link("Gate 2 decision", "Redraft stories", 1)
    link("Gate 2 decision", "Rejected", 2)
    link("Redraft stories", "Story input")

    # ---- Phase 3: tests, QA, bounded loop
    N.append(code_node("Test input", "return { json: $json };", (3080, 100), lib=False))
    N.append(chain_node("Test Designer", "test-designer.txt", (3300, 100)))
    N.append(model_node("Claude Sonnet · test designer", "test_designer", (3300, 320)))
    N.append(code_node("Check tests", """
const state = { ...$('Test input').item.json };
let data;
try { data = extractJson($json.text); } catch (e) { fail('Test Designer', e.message, $json.text); }
const problem = checkTests(data);
if (problem) fail('Test Designer', problem, $json.text);
state.tests = data;
return { json: state };
""", (3520, 100)))
    N.append(chain_node("QA Verifier", "qa-verifier.txt", (3740, 100)))
    N.append(model_node("Claude Opus · QA verifier", "qa_verifier", (3740, 320)))
    N.append(code_node("Check gaps & route", f"""
const MAX_LOOPS = {MAX_LOOPS};
const STORY_LEVEL = ['uncovered_requirement', 'scope_drift', 'inconsistency'];
const state = {{ ...$('Check tests').item.json }};
let gaps;
try {{ gaps = extractJson($json.text); }} catch (e) {{ fail('QA Verifier', e.message, $json.text); }}
const problem = checkGaps(gaps);
if (problem) fail('QA Verifier', problem, $json.text);
state.gap_report = gaps;
state.coverage = coverage(state.stories, state.tests);

const high = gaps.filter((g) => g.severity === 'high');
const pick = (types) => {{ const g = gaps.filter((x) => !types || types.includes(x.type)); return g.length ? JSON.stringify(g, null, 2) : '(none)'; }};
if (high.length && state.loops < MAX_LOOPS) {{
  state.loops += 1;
  if (high.some((g) => STORY_LEVEL.includes(g.type))) {{
    state.route = 0;                       // scope gap: back to the Story Writer (and Gate 2)
    state.feedback = pick(STORY_LEVEL);
    state.next_test_feedback = pick(['untested_criterion']);
  }} else {{
    state.route = 1;                       // thin tests only: back to the Test Designer
    state.feedback = pick(null);
  }}
}} else {{
  state.route = 2;                         // to the human for sign-off
  state.view = '<p><b>QA feedback loops used:</b> ' + state.loops + ' of ' + MAX_LOOPS +
    (high.length ? ' — high-severity gaps remain; read them before approving.' : '') + '</p>' +
    '<h3>QA gap report</h3>' + gapsHtml(gaps) + '<h3>Mechanical coverage check</h3>' + coverageHtml(state.coverage) +
    '<h3>Stories</h3>' + storiesHtml(state.stories) + '<h3>Tests</h3>' + testsHtml(state.tests);
}}
return {{ json: state }};
""", (3960, 100)))
    N.append(switch_node("Loop or sign off", "={{ $json.route }}", 3, (4180, 100)))
    N.append(gate_node("Gate 3 · sign-off", "Gate 3 of 3 — final sign-off",
                       "The QA Verifier has checked this package. Approve to finish and get the Delivery Spec, or Reject to stop.",
                       "={{ $json.view }}", ["Approve", "Reject"], (4400, 300), feedback=False))
    N.append(switch_node("Gate 3 decision", "={{ ['Approve', 'Reject'].indexOf($json.Decision) }}", 2, (4620, 300)))
    N.append(code_node("Assemble Delivery Spec", """
const s = $('Check gaps & route').item.json;
const spec = {
  feature_request: s.feature_request,
  status: 'approved',
  requirement: s.requirement,
  stories: s.stories,
  tests: s.tests,
  gap_report: s.gap_report,
  coverage: s.coverage,
  approvals: { gate1: true, gate2: true, gate3: true },
  loops: s.loops,
};
const html = '<h2>Delivery Spec — approved</h2>' +
  '<h3>1. Requirement</h3>' + requirementHtml(spec.requirement) +
  '<h3>2. User stories</h3>' + storiesHtml(spec.stories) +
  '<h3>3. Test cases</h3>' + testsHtml(spec.tests) +
  '<h3>4. QA gap report</h3>' + gapsHtml(spec.gap_report) + coverageHtml(spec.coverage) +
  '<h3>JSON</h3><p>Copy this, or open the execution in n8n to download it.</p><pre style="white-space:pre-wrap;text-align:left;font-size:12px">' + esc(JSON.stringify(spec, null, 2)) + '</pre>';
return { json: { spec, html } };
""", (4840, 200)))
    N.append(ending_node("Delivery Spec", "Delivery Spec", "={{ $json.html }}", (5060, 200)))
    N.append(ending_node("Rejected", "Stopped",
                         "=<h2>Run stopped</h2><p>A reviewer rejected this phase, so nothing after it was run.</p>"
                         "<p>Open the form again to start over with a clearer request.</p>", (5060, 520)))
    link("Stories approved", "Test input")
    link("Test input", "Test Designer")
    use_model("Claude Sonnet · test designer", "Test Designer")
    link("Test Designer", "Check tests")
    link("Check tests", "QA Verifier")
    use_model("Claude Opus · QA verifier", "QA Verifier")
    link("QA Verifier", "Check gaps & route")
    link("Check gaps & route", "Loop or sign off")
    link("Loop or sign off", "Story input", 0)
    link("Loop or sign off", "Test input", 1)
    link("Loop or sign off", "Gate 3 · sign-off", 2)
    link("Gate 3 · sign-off", "Gate 3 decision")
    link("Gate 3 decision", "Assemble Delivery Spec", 0)
    link("Gate 3 decision", "Rejected", 1)
    link("Assemble Delivery Spec", "Delivery Spec")

    sticky = {
        "parameters": {
            "content": "## Agentic SDLC Delivery Assistant\n\n**Setup:** open each of the four *Claude* model nodes "
                       "and pick your Anthropic credential (create one with your API key).\n\n**Run:** click "
                       "*Test workflow* (or *Execute workflow*), fill in the form, and review each gate on the "
                       "following form pages.\n\nRouting: Sonnet → Haiku → Sonnet → **Opus** (QA only). "
                       "High-severity gaps loop back (max 2).\n\nGenerated from `prompts/` by "
                       "`n8n/build_workflow.py` — edit the prompts there, not here.",
            "height": 300, "width": 420,
        },
        "id": node_id("Read me"), "name": "Read me", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
        "position": [-40, -80],
    }
    N.insert(0, sticky)

    return {
        "name": "Agentic SDLC Delivery Assistant",
        "nodes": N,
        "connections": C,
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "meta": {"templateCredsSetupCompleted": False},
        "tags": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit 1 if workflow.json is stale")
    args = parser.parse_args()
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("n8n/workflow.json is out of date. Run: python n8n/build_workflow.py", file=sys.stderr)
            return 1
        print("n8n/workflow.json is up to date.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(build()['nodes'])} nodes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
