"""
A summary written for ONE X-ray, plus suggested next steps for the dentist.

Everything here is plain rules, no second AI: the same findings always give the
same text, it works offline, and every sentence can be traced to a rule below.

What the detection model gives us per finding is only a condition, a box and a
confidence score. It cannot tell tooth numbers, caries depth or lesion size, so:
  - the "area" is an approximate region worked out from where the box sits;
  - every next step says "check / consider" and "if you confirm it";
  - findings the dentist marked "disagree" are left out of the next steps.

The NEXT_STEPS table comes from published guidelines (see "SmartDent next-steps guide",
https://claude.ai/artifact/BBNEiEyY7L7QzRbkbJ6i3D). A supervising dentist should check and edit it.
"""
from PIL import Image

from ml import CLASS_NAMES

# ---------------------------------------------------------------- the table to review

# For each condition: what to check first, and what to consider if the dentist confirms it.
# Order = which to look at first (infection before decay before gums before impactions).
NEXT_STEPS = {
    "Periapical lesion": {
        "check": "Test pulp sensibility (cold test or EPT) and tenderness to percussion of the teeth in the {areas}, "
                 "look for swelling or a sinus tract, and take a periapical X-ray. Note if the tooth is already root-filled.",
        "consider": "If you confirm it: root canal treatment for a restorable tooth, or retreatment (or apical surgery) "
                    "if it is already root-filled; extraction if it cannot be saved. Refer to an endodontist for complex cases.",
        "source": "ESE S3-level guideline, Treatment of pulpal and apical disease (2023)",
    },
    "Caries": {
        "check": "Examine the {areas} clinically (clean and dry), and take a bitewing X-ray to see how deep the lesion goes. "
                 "Note whether it looks active and the patient's caries risk.",
        "consider": "If you confirm it: lesions in enamel or the outer third of dentine with no cavity can be managed without "
                    "drilling (fluoride, diet and brushing advice, sealant or resin infiltration, monitoring). Active cavitated "
                    "dentine lesions usually need a minimally invasive restoration, with selective caries removal when deep.",
        "source": "FDI policy statement on carious lesions (2019); SDCEP caries guidance (2018)",
    },
    "Bone Loss": {
        "check": "Do full periodontal charting (pocket depths, bleeding, recession, mobility, furcations), paying attention "
                 "to the {areas}, then stage and grade the periodontitis. Ask about smoking and diabetes.",
        "consider": "If you confirm it, treat in steps: hygiene advice and risk-factor control, then cleaning below the gum "
                    "(scaling and root planing), re-assess, then supportive care. Refer to a periodontist for advanced or "
                    "fast-progressing disease.",
        "source": "EFP S3-level guideline, Treatment of stage I-III periodontitis (2020)",
    },
    "Impacted tooth": {
        "check": "Ask about pain, swelling or past infections, check the gum over the tooth in the {areas} and the tooth next "
                 "to it. Before any surgery, check how close it is to the nerve canal or sinus (CBCT if needed).",
        "consider": "If it causes no problems, keep and monitor it (NICE advises against removing healthy impacted wisdom teeth "
                    "as a precaution). Consider removal or an oral surgery referral for unrestorable decay, untreatable pulp "
                    "or periapical disease, abscess, resorption, cysts or repeated pericoronitis.",
        "source": "NICE TA1, Guidance on the extraction of wisdom teeth",
    },
}

# Extra notes that depend on the patient's age (only shown when the date of birth is known).
def age_note(label, age):
    if age is None:
        return None
    if label == "Impacted tooth" and age < 14:
        return "The patient is under 14: this may be a tooth that is still developing and has not erupted yet."
    if label == "Impacted tooth" and age < 26:
        return "At this age this is most often a wisdom tooth; its position can still change."
    if label == "Bone Loss" and age < 30:
        return "Marked bone loss is unusual under 30 and may point to fast-progressing (grade C) periodontitis."
    if label == "Caries" and age < 14:
        return "In a child, check whether the lesion is in a baby tooth or an adult tooth."
    return None


# ---------------------------------------------------------------- reading the boxes

HIGH, MODERATE = 0.70, 0.45
PLURALS = {"Caries": "caries", "Periapical lesion": "periapical lesions", "Impacted tooth": "impacted teeth", "Bone Loss": "bone loss"}


def confidence_band(confidence):
    if confidence >= HIGH:
        return "high"
    if confidence >= MODERATE:
        return "moderate"
    return "low"


def area_of(box, width, height):
    """
    Rough region of a box on a panoramic X-ray, e.g. "upper right back teeth".
    On a panoramic the patient's right is on the LEFT of the image, and the
    biting line is near the middle, so the upper jaw is the top half.
    """
    if not width or not height:
        return None
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
    jaw = "upper" if cy < 0.5 else "lower"
    off_centre = abs(cx - 0.5)
    if off_centre < 0.10:
        return f"{jaw} front teeth"
    side = "right" if cx < 0.5 else "left"          # patient's side
    teeth = "premolar area" if off_centre < 0.20 else "back teeth"
    return f"{jaw} {side} {teeth}"


def image_size(path):
    """Width and height of an image file, or (None, None) if it can't be read."""
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError):
        return None, None


def join_words(words):
    words = list(dict.fromkeys(w for w in words if w))   # drop blanks and repeats, keep order
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


# ---------------------------------------------------------------- the summary

def assess(findings, width=None, height=None, age=None, patient_name=None):
    """
    Returns a dict:
      summary  - one paragraph about this X-ray
      items    - per finding: label, area, band, confidence, review
      steps    - per condition (not rejected by the dentist): label, areas, check, consider, low, note
      rejected - how many findings the dentist disagreed with
      pending  - how many findings are not reviewed yet
    """
    items = [{"label": f["label"], "confidence": f["confidence"], "review": f.get("review"),
              "band": confidence_band(f["confidence"]), "area": area_of(f["box"], width, height)}
             for f in findings]
    rejected = sum(i["review"] == "disagree" for i in items)
    pending = sum(i["review"] is None for i in items)
    who = patient_name.split()[0] if patient_name else "this patient"
    who_age = f"{who} ({age})" if age is not None else who

    if not items:
        summary = (f"The AI did not mark any caries, periapical lesions, impacted teeth or bone loss on "
                   f"the panoramic X-ray of {who_age}. A clear result is not proof of health: check the whole image, "
                   f"including areas the model was not trained on.")
        return {"summary": summary, "items": items, "steps": [], "rejected": 0, "pending": 0}

    # One phrase per finding, strongest first: "possible caries in the upper right back teeth (high confidence, 81%)"
    phrases = []
    for i in sorted(items, key=lambda i: -i["confidence"]):
        where = f" in the {i['area']}" if i["area"] else ""
        phrase = f"possible {i['label'].lower()}{where} ({i['band']} confidence, {i['confidence']:.0%})"
        if i["review"] == "agree":
            phrase += ", which you agreed with"
        elif i["review"] == "disagree":
            phrase += ", which you rejected"
        phrases.append(phrase)
    summary = f"On the panoramic X-ray of {who_age}, the AI marked {plural(len(items), 'finding')}: {join_words(phrases)}."

    found = {i["label"] for i in items}
    clear = [PLURALS.get(n, n.lower()) for n in CLASS_NAMES if n not in found]
    if clear:
        summary += f" It did not mark any {join_words(clear)}."
    sides = {i["area"].split()[1] for i in items if i["area"] and i["area"].split()[1] in ("left", "right")}
    if len(sides) == 2:
        summary += " Findings are on both sides of the mouth."

    # Next steps: one per condition the dentist hasn't rejected, most urgent first
    kept = [i for i in items if i["review"] != "disagree"]
    steps = []
    for label in NEXT_STEPS:
        hits = [i for i in kept if i["label"] == label]
        if not hits:
            continue
        areas = join_words(i["area"] for i in hits) or "marked area"
        steps.append({
            "label": label,
            "count": len(hits),
            "areas": areas,
            "check": NEXT_STEPS[label]["check"].format(areas=areas),
            "consider": NEXT_STEPS[label]["consider"],
            "source": NEXT_STEPS[label]["source"],
            "low": all(i["band"] == "low" for i in hits),     # only weak evidence: look again first
            "agreed": any(i["review"] == "agree" for i in hits),
            "note": age_note(label, age),
        })
    if steps:
        summary += f" Suggested first check: the {steps[0]['label'].lower()}."
    return {"summary": summary, "items": items, "steps": steps, "rejected": rejected, "pending": pending}


def assess_xray(xray, path):
    """assess() for a stored X-ray: reads the image size and the patient's age."""
    if xray.result is None:
        return None
    width, height = image_size(path)
    return assess(xray.result.findings, width, height, xray.patient.age, xray.patient.name)
