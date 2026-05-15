"""
Humanizer Agent

Runs after every draft. Two-layer detection (heuristic + LLM), then a
rewriter that addresses the flagged passages. The rewriter uses the draft
model (the prose writer); the detector uses the judge model.

Important: the humanizer makes prose read less like AI. It does NOT change
KDP's disclosure category — the text is still AI-generated.
"""

import re
from collections import Counter
from .shared.llm import generate, generate_json
from .shared.memory import BookProject


# ── Heuristic detector ───────────────────────────────────────────────────

_AI_PHRASES = [
    r"\btapestry of\b",
    r"\bnavigate the (?:complexities|intricacies|nuances)\b",
    r"\bin the realm of\b",
    r"\bdelve into\b",
    r"\bmyriad\b",
    r"\bveritable\b",
    r"\bplethora\b",
    r"\btestament to\b",
    r"\bever-changing landscape\b",
    r"\bin a world where\b",
    r"\blittle did (?:he|she|they) know\b",
    r"\bmeanwhile,\s",
    r"\bweighed heavily on\b",
    r"\bsent shivers down\b",
    r"\bsent a chill\b",
    r"\bthick with tension\b",
    r"\bbated breath\b",
    r"\bhung in the air\b",
    r"\bnot lost on\b",
    r"\beyes (?:sparkled|glittered|glistened|twinkled)\b",
    r"\bsteeled (?:himself|herself|themselves)\b",
    r"\bcouldn't help but\b",
    r"\bwith renewed (?:purpose|determination|vigor)\b",
    r"\bonly time would tell\b",
    r"\bworlds apart\b",
    r"\bbreathed a sigh of relief\b",
    r"\bmind raced\b",
    r"\bheart pounding\b",
    r"\bspine tingled\b",
]

_FILTER_WORDS = [
    r"\b(?:she|he|they|I) felt\b",
    r"\b(?:she|he|they|I) saw\b",
    r"\b(?:she|he|they|I) heard\b",
    r"\b(?:she|he|they|I) noticed\b",
    r"\b(?:she|he|they|I) realised\b",
    r"\b(?:she|he|they|I) realized\b",
    r"\b(?:she|he|they|I) thought\b",
    r"\b(?:she|he|they|I) wondered\b",
    r"\b(?:she|he|they|I) could (?:feel|see|hear|sense)\b",
    r"\bseemed to\b",
    r"\bappeared to\b",
]

_NOT_JUST_BUT = re.compile(
    r"\b(?:(?:was|were|is|are|had|have|did|does|do)\s+not|"
    r"(?:wasn't|weren't|isn't|aren't|hadn't|haven't|didn't|doesn't|don't))"
    r"\s+(?:just|merely|only|simply)\s+\w+",
    re.IGNORECASE,
)
_SHORT_PARALLEL_TRIPLE = re.compile(
    r"\b(?:She|He|They|It)\s+(?:was|were|had|did)\b[^.!?]{2,40}[.!?]\s+"
    r"(?:She|He|They|It)\s+(?:was|were|had|did)\b[^.!?]{2,40}[.!?]\s+"
    r"(?:She|He|They|It)\s+(?:was|were|had|did)\b[^.!?]{2,40}[.!?]",
    re.IGNORECASE,
)
_AS_OPENER = re.compile(r"(?:^|\n)\s*As (?:the|a|an|his|her|their|I|she|he|they)\s+\w+", re.IGNORECASE)
_TRIPLE_PARALLEL = re.compile(r"\b(\w+ \w+)[,.]\s+\1[,.]\s+\1", re.IGNORECASE)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_PARA_SPLIT = re.compile(r"\n\s*\n")


def _heuristic_scan(text: str) -> dict:
    words = re.findall(r"[A-Za-z']+", text)
    n_words = max(1, len(words))
    sentences = _SENT_SPLIT.split(text.strip()) if text.strip() else []
    n_sents = max(1, len(sentences))

    hits = Counter()
    samples: dict[str, list[str]] = {}

    def _record(cat: str, found: list[str]):
        if not found:
            return
        hits[cat] += len(found)
        samples.setdefault(cat, [])
        for s in found[:3]:
            if s not in samples[cat]:
                samples[cat].append(s)

    em_dash_count = len(re.findall(r"—|--", text))
    em_dash_per_1k = (em_dash_count / n_words) * 1000
    if em_dash_per_1k > 4:
        hits["em_dash_overuse"] = em_dash_count
        samples["em_dash_overuse"] = [
            f"{em_dash_count} em-dashes in {n_words} words ({em_dash_per_1k:.1f}/1000 — high)"
        ]

    for pat in _AI_PHRASES:
        matches = re.findall(pat, text, re.IGNORECASE)
        if matches:
            _record("stock_phrases", matches)

    filter_total = 0
    filter_examples = []
    for pat in _FILTER_WORDS:
        matches = re.findall(pat, text, re.IGNORECASE)
        filter_total += len(matches)
        filter_examples.extend(matches[:2])
    if filter_total / n_words * 1000 > 5:
        hits["filter_words"] = filter_total
        samples["filter_words"] = [
            f"{filter_total} filter constructions in {n_words} words "
            f"({filter_total/n_words*1000:.1f}/1000 — high). Examples: "
            + ", ".join(filter_examples[:5])
        ]

    for m in _NOT_JUST_BUT.finditer(text):
        _record("not_just_but", [m.group(0).strip()[:120]])

    for m in _SHORT_PARALLEL_TRIPLE.finditer(text):
        _record("parallel_sentence_triple", [m.group(0).strip()[:160]])

    as_openers = list(_AS_OPENER.finditer(text))
    if len(as_openers) >= 4:
        hits["as_opener_overuse"] = len(as_openers)
        samples["as_opener_overuse"] = [
            f"{len(as_openers)} 'As [the/her/his...]' sentence-openers — "
            "AI loves this rhythm; vary sentence starts."
        ]

    sent_lens = [len(s.split()) for s in sentences]
    similar_pairs = sum(
        1 for a, b in zip(sent_lens, sent_lens[1:])
        if a > 0 and b > 0 and abs(a - b) <= 2 and 6 <= a <= 20
    )
    if similar_pairs / n_sents > 0.5 and n_sents > 20:
        hits["cadence_repetition"] = similar_pairs
        samples["cadence_repetition"] = [
            f"{similar_pairs}/{n_sents} adjacent sentences have similar lengths"
        ]

    paras = _PARA_SPLIT.split(text)
    short_endings = sum(
        1 for p in paras
        if p.strip() and len(p.strip().split("\n")[-1].split()) <= 6
        and len(p.strip().split()) > 30
    )
    if len(paras) > 6 and short_endings / max(1, len(paras)) > 0.5:
        hits["paragraph_punch_rhythm"] = short_endings
        samples["paragraph_punch_rhythm"] = [
            f"{short_endings}/{len(paras)} paragraphs end with a short punchline"
        ]

    trigram_starts = Counter()
    for s in sentences:
        toks = s.split()[:3]
        if len(toks) == 3:
            trigram_starts[" ".join(toks).lower()] += 1
    repeated_starts = {k: v for k, v in trigram_starts.items() if v >= 3}
    if repeated_starts:
        hits["repeated_sentence_starts"] = sum(repeated_starts.values())
        samples["repeated_sentence_starts"] = [
            f"'{k}' starts {v} sentences" for k, v in list(repeated_starts.items())[:3]
        ]

    for m in _TRIPLE_PARALLEL.finditer(text):
        _record("parallel_triplet", [m.group(0).strip()])

    weights = {
        "stock_phrases":              0.8,
        "em_dash_overuse":            0.5,
        "filter_words":               0.1,
        "not_just_but":               1.2,
        "as_opener_overuse":          0.3,
        "cadence_repetition":         0.05,
        "paragraph_punch_rhythm":     0.2,
        "repeated_sentence_starts":   0.4,
        "parallel_triplet":           1.5,
        "parallel_sentence_triple":   1.5,
    }
    raw = sum(weights.get(k, 0.0) * v for k, v in hits.items())
    ai_score = 1.0 + min(9.0, raw / 1.2)
    return {
        "hits":     dict(hits),
        "samples":  samples,
        "ai_score": round(ai_score, 2),
        "n_words":  n_words,
    }


# ── LLM detector ─────────────────────────────────────────────────────────

_DETECTOR_SYSTEM = """You are an editor specialising in detecting AI-generated
prose. You read a chapter and flag passages that sound machine-written.

Common AI tells:
- Em-dash overuse, especially for parentheticals.
- "Not just X, but Y" / "It wasn't merely X, it was Y".
- "As <subject> <verbed>, ..." sentence openers.
- Filter words separating reader from sensation ("she felt", "he saw").
- Stock metaphors and abstractions ("tension thick in the air", "tapestry of").
- Symmetrical paragraph rhythm.
- Three-beat parallel structures as decoration.
- Cadenced sentence lengths.
- Setting-mirrors-mood.
- Smooth transition adverbs.
- Over-explanation of feelings.

Be specific. Quote the line. Name the tell. Suggest a more human alternative.

Return ONLY this JSON shape:

{
  "tells": [
    {
      "quote":      "<the offending sentence or phrase>",
      "category":   "em_dash | not_just_but | as_opener | filter_word | stock_phrase | parallel_triplet | symmetric_rhythm | mood_mirror | smooth_transition | over_explanation | other",
      "fix_hint":   "<one-sentence suggestion>"
    }
  ],
  "ai_score": <1-10 int, 10 = unmistakeably AI>,
  "summary":  "<one paragraph: overall AI-ness diagnosis>"
}

A clean chapter scores 2-3. A heavily AI-flavoured one scores 7-9.
"""


def _llm_detect(text: str, judge_model: str) -> dict:
    try:
        data = generate_json(
            _DETECTOR_SYSTEM,
            f"Chapter to analyse:\n\n{text}",
            model=judge_model, role="judge",
            temperature=0.3, num_ctx=16384,
        )
    except Exception as e:
        return {"tells": [], "ai_score": 5, "summary": f"(detector error: {e})"}
    return data


# ── Rewriter ─────────────────────────────────────────────────────────────

_REWRITER_SYSTEM = """You are revising a chapter of a fantasy novel to read
less like AI-generated prose and more like a human author's writing.

You will be given:
- The chapter
- A list of specific passages flagged as AI-sounding, with categories and fix hints

REWRITE the entire chapter. Preserve plot beats, POV, characters, and
approximate length. Apply these heuristics throughout:

1. CUT em-dashes that wrap a parenthetical. Use periods or commas.
2. KILL "not just X, but Y" constructions. Replace with one direct statement.
3. VARY sentence openers. Don't start with "As ..." more than once or twice.
4. CUT filter words. Replace "she felt cold" with what the cold did to her body.
5. KILL stock phrases ("tension thick in the air", "tapestry of", etc.).
6. VARY sentence and paragraph rhythm.
7. RESIST setting-mirrors-mood.
8. ALLOW imperfect, slightly ungrammatical sentences.
9. USE contractions where natural.
10. CUT over-explained feelings.

Preserve: POV character and tense; plot events; named characters/places/magic.

Output ONLY the rewritten chapter as finished prose. No notes, no headings.
"""


def _llm_rewrite(text: str, tells: list[dict], heuristic_samples: dict,
                 draft_model: str, target_words: int) -> str:
    flagged_lines = []
    for t in tells[:20]:
        q = t.get("quote", "").strip().replace("\n", " ")[:200]
        cat = t.get("category", "")
        fix = t.get("fix_hint", "")
        if q:
            flagged_lines.append(f"- [{cat}] \"{q}\"  ({fix})")
    heuristic_lines = []
    for cat, exs in heuristic_samples.items():
        for ex in exs[:1]:
            heuristic_lines.append(f"- [{cat}] {ex}")

    user = f"""CHAPTER (target ~{target_words} words):

{text}

LLM-FLAGGED PASSAGES:
{chr(10).join(flagged_lines) if flagged_lines else "(none from LLM detector)"}

HEURISTIC FLAGS:
{chr(10).join(heuristic_lines) if heuristic_lines else "(none)"}

Rewrite the full chapter now applying the rules in the system prompt.
"""
    out = generate(
        _REWRITER_SYSTEM, user,
        model=draft_model, role="draft",
        temperature=0.85, num_ctx=16384, max_tokens=8192,
    )
    return out.strip()


def run(project: BookProject, chapter_text: str, *,
        max_passes: int = 2,
        ai_score_target: float = 3.5,
        use_llm_detector: bool = True) -> dict:
    print("  [Humanizer] Scanning for AI-tells …")
    initial = _heuristic_scan(chapter_text)
    heur_score = initial["ai_score"]
    print(f"    heuristic score: {heur_score}  (hits: {dict(initial['hits']) or 'none'})")

    llm_initial = {"tells": [], "ai_score": 0, "summary": ""}
    if use_llm_detector:
        llm_initial = _llm_detect(chapter_text, project.judge_model)
        llm_score = llm_initial.get("ai_score", 0)
        n_tells = len(llm_initial.get("tells", []))
        print(f"    LLM detector score: {llm_score}  ({n_tells} specific tells)")

    combined_before = round(max(heur_score, llm_initial.get("ai_score", 0)), 2)

    text = chapter_text
    summaries = []
    passes = 0
    tells_history = [{"heuristic": initial, "llm": llm_initial}]

    while passes < max_passes:
        if combined_before <= ai_score_target:
            print(f"  [Humanizer] AI-score {combined_before} ≤ target {ai_score_target}; "
                  f"no rewrite needed.")
            break
        passes += 1
        print(f"  [Humanizer] Pass {passes}: rewriting …")
        new_text = _llm_rewrite(
            text,
            llm_initial.get("tells", []),
            initial["samples"],
            project.draft_model,
            project.target_words_per_chapter,
        )
        if not new_text or len(new_text.split()) < 200:
            print("  [Humanizer] Rewrite suspiciously short; keeping previous draft.")
            break

        heur2 = _heuristic_scan(new_text)
        llm2  = _llm_detect(new_text, project.judge_model) if use_llm_detector \
            else {"tells": [], "ai_score": 0}
        new_combined = round(max(heur2["ai_score"], llm2.get("ai_score", 0)), 2)
        print(f"    after pass {passes}: combined ai-score {new_combined}  "
              f"(was {combined_before})")
        summaries.append(llm2.get("summary", ""))
        tells_history.append({"heuristic": heur2, "llm": llm2})

        if new_combined < combined_before:
            text = new_text
            combined_before = new_combined
            initial = heur2
            llm_initial = llm2
        else:
            print("  [Humanizer] Pass did not improve score; stopping.")
            break

        if combined_before <= ai_score_target:
            print(f"  [Humanizer] Reached target score {ai_score_target} at pass {passes}.")
            break

    final_heur = _heuristic_scan(text)
    final_llm  = llm_initial if passes > 0 else (
        _llm_detect(text, project.judge_model) if use_llm_detector
        else {"tells": [], "ai_score": 0}
    )
    return {
        "text":            text,
        "passes":          passes,
        "ai_score_before": tells_history[0]["heuristic"]["ai_score"],
        "ai_score_after":  final_heur["ai_score"],
        "llm_score_before": tells_history[0]["llm"].get("ai_score", 0),
        "llm_score_after":  final_llm.get("ai_score", 0),
        "tells_before":    tells_history[0]["llm"].get("tells", []),
        "tells_after":     final_llm.get("tells", []),
        "summaries":       summaries,
        "heuristic_hits_before": tells_history[0]["heuristic"]["hits"],
        "heuristic_hits_after":  final_heur["hits"],
    }
