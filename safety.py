import re

from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# Fail closed: when we can't trust the classification, treat the question
# conservatively rather than routing it straight to a confident how-to answer.
_FALLBACK_TIER = "caution"

_SYSTEM_PROMPT = """You are a home-repair safety classifier. Classify the user's repair question into \
exactly one of three tiers, judging by the worst realistic outcome if an untrained \
homeowner gets the repair wrong.

TIERS:
- safe: Routine maintenance or a low-risk repair done with basic tools, no permit, \
and no license, where the worst outcome of a mistake is cosmetic damage or a broken \
fixture — never fire, flooding, gas, structural failure, or injury.
- caution: A like-for-like repair on an EXISTING water or electrical fixture (no new \
wiring, pipe, or circuit), doable without a permit, where a mistake has real cost or \
mild injury risk but stays recoverable (tripped breaker, a leak you can shut off, or \
a redo).
- refuse: Any repair where a mistake can cause fire, flooding, structural collapse, a \
gas leak, serious injury, or death — or that legally requires a permit or licensed \
professional. This includes ALL new electrical circuits/outlets/wiring, panel or \
service-entrance work, ANY gas work, wall removal, water-heater replacement, and \
running new plumbing lines.

THE DECISIVE RULE (caution vs. refuse):
Replacing or repairing an EXISTING fixture at the same location with no new wiring, \
pipe, or circuit is caution. ADDING anything new — a new outlet, switch, circuit, or \
plumbing line, or any work that runs new wire or cuts into a gas line — is refuse, \
even when the user frames it as small ("just move it a few inches," "just extend it a \
little"). Classify by what the work actually requires, not how it is framed. Gas, \
electrical panels, wall removal, and water-heater replacement are always refuse. When \
genuinely torn between two tiers, choose the more restrictive one.

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
TIER: <safe | caution | refuse>"""


def _parse_response(text: str) -> dict | None:
    """Extract and validate (tier, reason) from the raw model response.

    Returns a {"tier", "reason"} dict only when a recognized tier is found;
    returns None when the response can't be parsed or the tier isn't valid,
    so the caller can fail closed.
    """
    tier_match = re.search(r"TIER:\s*(.+)", text, re.IGNORECASE)
    if not tier_match:
        return None

    # Take only the first word after "TIER:", then strip surrounding quotes
    # and punctuation so "Refuse", "refuse.", and '"refuse"' all normalize.
    raw_tier = tier_match.group(1).strip().split()[0] if tier_match.group(1).strip() else ""
    tier = raw_tier.strip("\"'`.,:;!").lower()
    if tier not in VALID_TIERS:
        return None

    reason_match = re.search(r"REASON:\s*(.+)", text, re.IGNORECASE)
    reason = reason_match.group(1).strip() if reason_match else "No reason provided."

    return {"tier": tier, "reason": reason}


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    TODO — Milestone 1:

    Before writing any code, complete specs/classifier-spec.md. The blank fields
    there are the decisions that drive this implementation — prompt design, tier
    definitions, output format, and edge case handling.

    Your implementation should:
      1. Build a prompt using your tier definitions that asks the LLM to classify
         the question and explain its reasoning
      2. Send a single chat completion request (no tools, no history)
      3. Parse the tier and reason out of the raw response text
      4. Validate the tier against VALID_TIERS; fall back to "caution" if the
         response can't be parsed or the tier isn't recognized
      5. Return {"tier": ..., "reason": ...}

    Returns a dict with:
      - "tier"   : str — one of "safe", "caution", "refuse"
      - "reason" : str — a brief explanation of why this tier was assigned

    The three tiers:
      - "safe"    : routine, low-risk repairs most homeowners can handle safely
      - "caution" : doable with care, but mistakes have real cost or mild risk
      - "refuse"  : high-risk repairs that require a licensed professional —
                    mistakes can cause fire, flooding, injury, or structural damage
    """
    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Classify this home repair question:\n\n{question}",
                },
            ],
        )
        raw = completion.choices[0].message.content or ""
    except Exception as exc:  # network/auth/rate-limit — fail closed
        return {
            "tier": _FALLBACK_TIER,
            "reason": f"Could not classify (API error: {exc}); treating conservatively.",
        }

    parsed = _parse_response(raw)
    if parsed is None:
        return {
            "tier": _FALLBACK_TIER,
            "reason": "Could not reliably parse a valid tier from the model; treating this question conservatively.",
        }

    return parsed
