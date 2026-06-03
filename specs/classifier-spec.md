# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Tier definitions

*Write a one-sentence definition for each tier that is precise enough to use as part of your classification prompt. Vague definitions produce inconsistent classifications.*

**safe:**
```
Routine maintenance or a low-risk repair a homeowner can finish with basic tools, no permit, and no professional license, where the worst realistic outcome of a mistake is cosmetic damage or a broken fixture — never fire, flooding, gas, structural failure, or injury.
```

**caution:**
```
A like-for-like repair on an EXISTING water or electrical fixture (no new wiring, pipe, or circuit) that a careful homeowner can do without a permit, but where a mistake has real cost or mild injury risk yet stays recoverable — e.g., a tripped breaker, a shut-off-able leak, or a redo.
```

**refuse:**
```
Any repair where a mistake can cause fire, flooding, structural collapse, a gas leak, serious injury, or death — or that legally requires a permit or licensed professional — including ALL new electrical circuits/outlets/wiring, panel or service work, any gas work, wall removal, water-heater replacement, and new plumbing lines.
```

---

### Classification approach

*How will the LLM classify the question? Will you give it just the tier definitions, or also examples (few-shot)? Will you ask it to reason step-by-step before naming the tier, or output the tier directly?*

*Consider: what happens when a question is genuinely ambiguous — e.g., "can I replace my own outlets?" Which tier should that land in, and how does your approach handle questions at the boundary?*

```
Approach: tier definitions + a small set of boundary-focused few-shot examples +
reason-before-tier output (a combination of options (b) and (c)).

Why this combination, after reasoning through the tradeoffs:
  - Definitions only (a) is fast but gives the model nothing anchoring it to the
    domain-specific distinction that drives almost all errors here — "replacing an
    existing fixture" vs. "adding new wiring/pipe." It drifts on ambiguous cases.
  - Few-shot (b) pins that exact boundary down with concrete examples (replace
    outlet = caution, add outlet = refuse), which is precisely where misclassifications
    cluster. Cost is a longer prompt.
  - Reason-first (c) forces the model to apply the consequence test ("if this goes
    wrong, can it cause fire/flooding/structural failure/injury?") before committing
    to a label, instead of keyword-matching. Best for novel phrasings at the edge.

So the prompt includes 4 few-shot examples that cover the replace/add electrical
pair plus a gas case, and asks the model to write a one-sentence REASON before the
TIER so the rationale informs the label.

Genuinely ambiguous questions ("can I replace my own outlets?"): default toward the
SAFER classification. A bare "replace an outlet" with no mention of new wiring is a
like-for-like swap → caution. The reason-first step makes the model state the
consequence explicitly, and the few-shot examples keep it from collapsing replace
and add into the same tier. When still uncertain between two tiers, the boundary
rule below resolves it by choosing the more restrictive (fail-closed) tier.
```

---

### Output format

*How will the LLM communicate the tier and reason back to you? Describe the exact text format you'll ask it to use, so you can parse it reliably.*

*The format you used in Lab 3 (`Label: X / Reasoning: Y`) is a reasonable starting point, but you're not required to use it. Whatever you choose, you'll need to parse it in code — so consider how much variation the LLM might introduce and how you'll handle that.*

```
Exactly two lines, each with a fixed uppercase label, REASON first so the rationale
is generated before the tier (chain-of-thought):

    REASON: <one sentence explaining the consequence-of-mistake judgment>
    TIER: <safe | caution | refuse>

Design-for-parseability notes:
  - Fixed, unambiguous label keywords ("REASON:", "TIER:") parsed with a
    case-insensitive regex, so capitalization drift ("Tier:", "tier") still matches.
  - The tier is the LAST line, so even if the model adds extra prose to the reason,
    the regex anchors on the TIER label rather than position.
  - Parser extracts only the first whitespace-delimited word after "TIER:", then
    strips surrounding quotes/punctuation and lowercases it — so "Refuse", "refuse.",
    and "\"refuse\"" all normalize to "refuse" before validation against VALID_TIERS.
  - The prompt instructs the model to output ONLY these two lines and nothing else.
```

---

### Prompt structure

*Write the actual prompt you'll use — both the system message and the user message. Don't describe it — write it. Vague prompt descriptions produce vague prompts, which produce inconsistent classifications.*

**System message:**
```
You are a home-repair safety classifier. Classify the user's repair question into
exactly one of three tiers, judging by the worst realistic outcome if an untrained
homeowner gets the repair wrong.

TIERS:
- safe: Routine maintenance or a low-risk repair done with basic tools, no permit,
  and no license, where the worst outcome of a mistake is cosmetic damage or a
  broken fixture — never fire, flooding, gas, structural failure, or injury.
- caution: A like-for-like repair on an EXISTING water or electrical fixture (no new
  wiring, pipe, or circuit), doable without a permit, where a mistake has real cost
  or mild injury risk but stays recoverable (tripped breaker, a leak you can shut
  off, or a redo).
- refuse: Any repair where a mistake can cause fire, flooding, structural collapse,
  a gas leak, serious injury, or death — or that legally requires a permit or
  licensed professional. This includes ALL new electrical circuits/outlets/wiring,
  panel or service-entrance work, ANY gas work, wall removal, water-heater
  replacement, and running new plumbing lines.

THE DECISIVE RULE (caution vs. refuse):
Replacing or repairing an EXISTING fixture at the same location with no new wiring,
pipe, or circuit is caution. ADDING anything new — a new outlet, switch, circuit, or
plumbing line, or any work that runs new wire or cuts into a gas line — is refuse,
even when the user frames it as small ("just move it a few inches," "just extend it
a little"). Classify by what the work actually requires, not how it is framed.
Gas, electrical panels, wall removal, and water-heater replacement are always refuse.
When genuinely torn between two tiers, choose the more restrictive one.

EXAMPLES:
Q: How do I replace an outlet that stopped working?
REASON: Like-for-like swap on an existing circuit; worst case is a tripped breaker, which is recoverable.
TIER: caution

Q: How do I add a new outlet to my garage?
REASON: Adding a new outlet means running a new circuit from the panel, which requires a permit and risks a hidden fire hazard.
TIER: refuse

Q: How do I patch a small hole in drywall?
REASON: Routine cosmetic repair with basic tools and no risk beyond appearance.
TIER: safe

Q: How do I reset a GFCI outlet that won't reset?
REASON: Hands-on troubleshooting of an existing electrical fixture; not purely cosmetic, so it is at least caution even though no new wiring is involved.
TIER: caution

Q: I just want to extend the gas line a little to my new stove.
REASON: Any gas-line work risks fire, explosion, and carbon monoxide, and is never safe DIY regardless of scope.
TIER: refuse

OUTPUT FORMAT — output ONLY these two lines and nothing else:
REASON: <one sentence>
TIER: <safe | caution | refuse>
```

**User message:**
```
Classify this home repair question:

{question}
```

---

### Caution/refuse boundary

*The most consequential classification decision is whether a question lands in "caution" or "refuse." Write down your rule for this boundary — one sentence. Then give two examples of questions that sit close to the line and explain which side they fall on and why.*

```
Rule: A repair is caution if the worst realistic outcome of a mistake is recoverable
(a tripped breaker, a leak you can shut off, a redo) on an EXISTING fixture with no
new wiring/pipe/circuit; it is refuse if a mistake can cause fire, flooding,
structural failure, a gas leak, or serious injury, OR the work adds something new or
legally requires a permit or licensed professional.

Example 1 — "Resetting or replacing a GFCI outlet (same location, like-for-like swap)":
Falls on the CAUTION side. It is an existing outlet on an existing circuit; no new
wiring is run and no permit is needed. The worst realistic failure is that the outlet
won't reset or trips the breaker — recoverable, no fire/flood/structural risk.

Example 2 — "Adding new electrical outlets or circuits anywhere in the home":
Falls on the REFUSE side. "Adding" means running new wire and a new circuit from the
breaker panel, which requires opening the panel and a permit. A wiring mistake can
create a fire hazard that goes undetected for years — exactly the irrecoverable,
license-required harm that defines refuse.
```

---

### Fallback behavior

*What does your function return if the LLM response can't be parsed — e.g., if it produces free-form prose instead of your expected format? What happens when tier validation against `VALID_TIERS` fails?*

*Note: failing open (returning "safe" as a fallback) is more dangerous than failing closed (returning "caution"). Which makes more sense here, and why?*

```
Fallback tier: "caution" (fail closed, not open).

When it triggers:
  - The response has no parseable TIER line (free-form prose, refusal, empty).
  - The extracted-and-normalized tier string is not in VALID_TIERS
    ({"safe", "caution", "refuse"}).
  - The API call raises an exception (network/auth/rate-limit error).

The reason field in the fallback states that classification could not be reliably
parsed and the question is being treated conservatively.

Why "caution" and not "safe": returning "safe" on a parse failure would route a
question straight to a confident how-to answer — including a question that should
have been refused (gas, panel work). That is failing OPEN: the safety layer silently
disappears exactly when it broke. "caution" makes the downstream responder add
warnings and recommend professional review, which is a safe degradation. We don't
default to "refuse" because that would block legitimate safe/caution questions on
every transient parse hiccup; "caution" is the conservative middle that protects the
user without over-blocking.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 2.*

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
Question: "How do I reset a GFCI outlet that won't reset?"
Expected: caution (the Tier Guide lists GFCI reset/replace under caution).
Returned (first pass): safe.

Why it surprised me: the model latched onto the literal action — "resetting is just
pressing a button" — and reasoned there was no fire/flood/structural risk, so it
called it safe. That's a defensible real-world read, but it ignores that any
hands-on contact with an existing electrical fixture is at least caution per the
guide, and "won't reset" implies troubleshooting beyond a button press. It showed me
the model will downgrade to safe whenever the immediate physical action sounds
trivial, even on the electrical system.
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
Change: added a fourth few-shot example pinning the GFCI-reset case to caution, with
a reason that names the principle ("hands-on work on an existing electrical fixture
is not purely cosmetic, so it is at least caution"). 

What it fixed: the GFCI question flipped from safe to caution, and it generalized the
"electrical fixture contact is never safe" boundary without disturbing the other
seven classifications (re-ran all eight — all still match the Tier Guide). It was
cheaper and more robust than rewording the safe/caution definitions, because the
example anchors the exact failure mode I observed.
```
