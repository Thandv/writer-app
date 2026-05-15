"""
Corpus builder for the writer pipeline.

  python -m writer_app.shared.corpus build       # download all + write style cards
  python -m writer_app.shared.corpus build --gutenberg-only
  python -m writer_app.shared.corpus list

The corpus has three layers:
  gutenberg/    — full text of public-domain fantasy classics
  style_cards/  — markdown descriptions of modern bestseller voices
                  (fair-use commentary — no copyrighted prose)
  craft/        — beat sheets, magic system templates, progression patterns

Path resolution: WRITER_CORPUS_DIR env override > dev (corpus/ next to
repo root) > installed user data dir (~/.local/share/writer-app/corpus/).
"""

import sys
import os
import re
import urllib.request
import urllib.error
from pathlib import Path


def resolve_corpus_dir() -> Path:
    """Find the right corpus directory for this run.

    Priority:
      1. $WRITER_CORPUS_DIR (explicit override)
      2. <repo>/corpus/  if running from a checkout (style_cards populated)
      3. ~/.local/share/writer-app/corpus/  (installed default)
    """
    env = os.environ.get("WRITER_CORPUS_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    # src/writer_app/shared/corpus.py → parents[3] = repo root in dev layout
    here = Path(__file__).resolve()
    repo_corpus = here.parents[3] / "corpus" if len(here.parents) >= 4 else None
    if repo_corpus and repo_corpus.exists() and (repo_corpus / "style_cards").exists():
        return repo_corpus
    return Path.home() / ".local" / "share" / "writer-app" / "corpus"


CORPUS_DIR = resolve_corpus_dir()


# ── Project Gutenberg titles ─────────────────────────────────────────────
GUTENBERG = [
    ("dunsany_king_of_elflands_daughter.txt",  20861, "Dunsany — The King of Elfland's Daughter"),
    ("dunsany_gods_of_pegana.txt",             7477,  "Dunsany — The Gods of Pegāna"),
    ("dunsany_book_of_wonder.txt",             11461, "Dunsany — The Book of Wonder"),
    ("morris_well_at_the_worlds_end.txt",      4673,  "Morris — The Well at the World's End (vol 1)"),
    ("morris_wood_beyond_the_world.txt",       3055,  "Morris — The Wood Beyond the World"),
    ("macdonald_phantastes.txt",               325,   "MacDonald — Phantastes"),
    ("macdonald_lilith.txt",                   1640,  "MacDonald — Lilith"),
    ("macdonald_princess_and_the_goblin.txt",  708,   "MacDonald — The Princess and the Goblin"),
    ("eddison_worm_ouroboros.txt",             10744, "Eddison — The Worm Ouroboros"),
    ("howard_red_nails.txt",                   32759, "Howard — Red Nails (Conan)"),
    ("howard_gods_of_the_north.txt",           42182, "Howard — Gods of the North (Conan)"),
    ("lovecraft_dream_quest.txt",              31791, "Lovecraft — The Dream-Quest of Unknown Kadath"),
    ("cabell_jurgen.txt",                      8771,  "Cabell — Jurgen"),
    ("mirrlees_lud_in_the_mist.txt",           53985, "Mirrlees — Lud-in-the-Mist"),
    ("lang_blue_fairy_book.txt",               503,   "Lang — The Blue Fairy Book"),
    ("kingsley_heroes.txt",                    677,   "Kingsley — The Heroes (Greek myth retellings)"),
    ("malory_morte_darthur_v1.txt",            1251,  "Malory — Le Morte d'Arthur (vol 1)"),
]


def _gutenberg_url(book_id: int) -> str:
    return f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"


def _strip_gutenberg_boilerplate(text: str) -> str:
    start_pat = re.compile(r"\*\*\*\s*START OF (?:THE |THIS )?PROJECT GUTENBERG.*?\*\*\*",
                           re.IGNORECASE | re.DOTALL)
    end_pat   = re.compile(r"\*\*\*\s*END OF (?:THE |THIS )?PROJECT GUTENBERG",
                           re.IGNORECASE | re.DOTALL)
    m = start_pat.search(text)
    if m:
        text = text[m.end():]
    m = end_pat.search(text)
    if m:
        text = text[:m.start()]
    return text.strip()


def _download_gutenberg(label: str, book_id: int, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 5000:
        print(f"  ✓ {label}  (already have)")
        return True
    url = _gutenberg_url(book_id)
    try:
        print(f"  ↓ {label} … ", end="", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "writer-app/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        cleaned = _strip_gutenberg_boilerplate(raw)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(cleaned, encoding="utf-8")
        print(f"ok ({len(cleaned):,} chars)")
        return True
    except urllib.error.HTTPError as e:
        print(f"FAILED ({e.code})")
        return False
    except Exception as e:
        print(f"FAILED ({e})")
        return False


def build_gutenberg():
    print(f"\nDownloading public-domain corpus to {CORPUS_DIR / 'gutenberg'}\n")
    ok = 0
    for fname, book_id, label in GUTENBERG:
        dest = CORPUS_DIR / "gutenberg" / fname
        if _download_gutenberg(label, book_id, dest):
            ok += 1
    print(f"\n{ok}/{len(GUTENBERG)} downloaded.\n")


# ── Style cards — fair-use descriptions of modern bestseller voices ──────
STYLE_CARDS = {
    "sanderson_clarity.md": """\
# Style: Brandon Sanderson — Clarity-First Epic / Hard Magic

## Voice
Clean, transparent prose. Sentences are workmanlike; their job is to deliver
plot and character clearly, not to call attention to themselves. Vocabulary
stays accessible. Imagery is functional, not decorative. The reader is never
confused about who is doing what to whom.

## What this voice does well
- POV switches with clear scene breaks; each POV chapter has a goal and an outcome.
- Magic systems with rules, costs, and limits. The reader can predict what is
  possible and what is not. Reveals come from clever application, not new rules.
- Promises → progress → payoff. Setups are paid off within the same book or
  flagged for a sequel.

## Sentence-level habits
- Short to medium sentences. Compound sentences over complex ones.
- Dialogue tags are mostly "said" with minimal adverbs.
- Internal thought rendered in italics or as direct narration, clearly marked.
- Sensory detail is selective — one or two anchoring details per setting, then
  on with the scene.

## Drafter cues
- Lead each scene with: where, who, what they want.
- One concrete physical anchor (object, weather, posture) in the first paragraph.
- Magic must follow rules already established or being established.
- Resist purple prose. If a line feels "literary," ask whether it earns its place.
""",
    "abercrombie_grimdark.md": """\
# Style: Joe Abercrombie — Grimdark POV with Black Comedy

## Voice
Tight third person, each POV a distinct interior voice. Dry, cynical,
mordantly funny. Bodies hurt. Cleverness is punished. Heroism is mostly
self-deception, often someone else's. Sentence rhythm is punchy and modern,
willing to break grammar for cadence.

## What this voice does well
- POV interiority that sounds like a real person thinking, complete with
  petty grievances, self-justification, and contradictions.
- Violence with consequence — fights are short, ugly, and have aftermath.
- Reversals of expectation in scene-level beats: the rescue fails, the wise
  mentor is wrong, the hero's plan was always going to get someone killed.

## Sentence-level habits
- Fragments. For emphasis.
- Free indirect discourse: narration drifts into the POV's idiom without
  italics or quote marks.
- Black-comic similes. "Hope is like an old whore: she keeps coming back
  even after you've thrown her down the stairs." (paraphrasing the texture.)
- Dialogue is laconic. People say less than they mean. Silences land.

## Drafter cues
- Pick the POV's worst trait and let it taint their narration.
- Show plans going wrong, not right.
- Bodies are vulnerable. Wounds are not forgotten next chapter.
- If a scene ends on a heroic beat, ask: what does it cost?
""",
    "rothfuss_lyrical_first_person.md": """\
# Style: Patrick Rothfuss — Lyrical First-Person Frame

## Voice
First-person retrospective from a verbal, self-mythologising narrator. Cadenced,
musical, often verging on incantation. Repetition is structural ("There was a
silence of three parts."). The narrator is unreliable in the way all storytellers
are unreliable: shaping events for an audience.

## What this voice does well
- The frame story lets the present-day Kvothe undercut the heroic legend.
- Set-piece episodes (the Eolian, the trial) treated as theatrical performances.
- Lavish attention to craft — naming, music, sympathy — as proxies for
  worldbuilding and character growth.

## Sentence-level habits
- Anaphora and parallel structure: repeated openings ("My name is...").
- Long, balanced sentences alternated with sharp short ones.
- Sensuous, specific physical detail — instruments, food, women's hands.
- Direct address to the listener inside the frame.

## Drafter cues
- Pick a strong present-tense voice for the frame, even if the story is past.
- Repeat to structure: openings of paragraphs, key images.
- Slow when something matters; accelerate through transitions.
- Earn the lyrical lines with austere ones around them.
""",
    "erikson_density.md": """\
# Style: Steven Erikson — Dense Multi-POV Epic

## Voice
Many POVs, often introduced without a roadmap. Philosophical, mythopoeic,
willing to digress into meditation on power, history, or grief. Time-scales
collapse: ancient gods and present-day soldiers occupy the same paragraph.
The reader is trusted, almost punished, by the lack of hand-holding.

## What this voice does well
- Convergence: many storylines pulling toward one geographical or temporal
  point over hundreds of pages.
- Voice differentiation across POVs through diction, sentence length, and
  thematic preoccupation.
- Marines and grunts as POVs alongside ascendants — the small-scale grounds
  the cosmic.

## Sentence-level habits
- Long subordinated sentences for reflection; clipped sentences for combat.
- Aphoristic openings ("There are truths only the wounded recognise.").
- POV-specific obsessions — one character notices wood-grain, another notices
  bloodlines, another notices weather.
- Italicised meditations breaking the action.

## Drafter cues
- Each POV must want something different and notice different things.
- Trust the reader. Don't over-explain magic, geography, or politics.
- Let philosophy live in the narration but tie it to action in the same scene.
- Convergence is the engine — every chapter nudges the threads closer.
""",
    "jemisin_second_person.md": """\
# Style: N. K. Jemisin — Second-Person, Fragmented Time, Modern Diction

## Voice
A second-person "you" voice braided with limited-third strands; tense slips
between past and present. Diction is contemporary, often blunt. Anger and grief
sit on the surface. Worldbuilding is grounded in geology, race, and the
materiality of power.

## What this voice does well
- The "you" creates intimacy and complicity — the reader is implicated in
  what's done to and by the protagonist.
- Withheld information used as structural tension: the reader knows something
  important is being held back, and the form of withholding becomes meaning.
- Earthquakes, tectonics, broken systems as both literal and political.

## Sentence-level habits
- Sentence fragments. Often. To hit.
- Direct address: "You will not believe what they did next."
- Parentheticals carrying the narrator's commentary, sometimes pages later.
- Profanity used precisely, never as decoration.

## Drafter cues
- If you use second person, commit to the choice — let it shape every line.
- Don't telegraph the structural reveal; let form do the work.
- Modern diction is allowed even in invented worlds — but use it deliberately.
""",
    "progression_royalroad.md": """\
# Style: Progression Fantasy (Royal Road / Web-Serial conventions)

## Voice
First-person or close-third. Functional prose — the reader is here for the
system, the growth, the wins. Internal monologue carries plot logistics:
plans, system messages, training schedules. Chapter ends on a hook or
breakthrough.

## What this voice does well
- Visible, tier-based power systems (cultivation realms, system levels,
  skill trees). The reader can map progress.
- Training arcs and breakthrough beats — the slow climb followed by a clear
  level-up. Earned via specific, novel application of the system.
- High chapter-turn frequency. Each chapter delivers a small win, a setback,
  or a new system reveal.

## Structural habits
- Cold opens in medias res, then a beat of orientation.
- System messages / status screens / cultivator-tier descriptions used as
  scene punctuation.
- Antagonists scaled to current tier; old enemies become trivial by design,
  setting up new threat tiers.
- Power-up costs that constrain choices later (mana debts, qi deviations,
  body burden).

## Drafter cues
- Make the system legible. Every new ability has a cost and a rule.
- Show the protagonist measurably stronger this chapter than three chapters ago.
- End most chapters on a question, a setback, or a system event.
- Don't be ashamed of clarity; this genre rewards "and then" momentum.
""",
    "le_guin_quiet_clarity.md": """\
# Style: Ursula K. Le Guin — Quiet Anthropological Clarity

## Voice
Clear, classical sentences. Anthropologist's eye for custom, ritual, naming.
Politics and ecology surfaced through detail, never lectured. Restraint at
moments of high emotion — the page goes quiet where lesser writers would
go loud.

## What this voice does well
- Worldbuilding through small daily life: tea, weaving, walking patterns,
  forms of address.
- Moral seriousness without moralising. The reader is treated as a thinking adult.
- Endings that turn rather than climax — the final image reframes the story.

## Sentence-level habits
- Plain Anglo-Saxon vocabulary. Latinate words used sparingly, with weight.
- Short paragraphs. White space. The page breathes.
- Names and naming as theme and craft (A Wizard of Earthsea).
- The proverb or aphorism as a closing line.

## Drafter cues
- Trust restraint. The biggest emotion often lands quietest.
- Pick one or two ethnographic details per scene to do the worldbuilding.
- Resist epic gestures; the small and exact is more lasting.
""",
}

# ── Craft notes ──────────────────────────────────────────────────────────
CRAFT_NOTES = {
    "scene_structure.md": """\
# Scene Structure: Goal, Conflict, Outcome

A scene that works has three components, identifiable in a one-line summary:

1. **Goal.** The POV character wants something concrete in this scene.
   "Find out who killed her sister." "Survive the duel." "Get the loan."
2. **Conflict.** Something opposes the goal: another character, the world,
   the POV's own self.
3. **Outcome.** One of:
   - Yes (got it) — usually too easy, low tension.
   - No (failed) — sets up the next scene with a worse situation.
   - Yes, but... — got it, but at a cost or with a complication.
   - No, and... — failed, and now things are worse.

The strongest options are "Yes, but..." and "No, and...". They generate the
next scene automatically because the outcome is unstable.

## Sequel beats (between scenes)
After a scene, the POV processes it in four micro-beats:
**reaction → dilemma → decision → new goal**. Sequels are short — sometimes
one paragraph. They convert outcome into the next scene's goal.

## Drafter checklist
- [ ] Can I name the POV's goal in one sentence?
- [ ] Is there an opposing force visible in the first page of the scene?
- [ ] Does the outcome change the POV's situation, not just the plot?
""",
    "promises_and_payoffs.md": """\
# Promises and Payoffs

Every reveal, plot twist, or emotional beat must have been promised earlier
in the book. The earliest promise can be very quiet — a name dropped, a habit
shown, a single line of dialogue. The payoff feels earned when the reader can
locate the promise in retrospect.

## Types of promise
- **Character promise.** A trait, fear, or wound shown in the opening 50 pages
  must be addressed by the climax.
- **Plot promise.** A mystery, threat, or question raised in act one must
  be answered (or transformed) by act three.
- **World promise.** A magical system rule, faction, or place introduced in
  passing must matter later, or it shouldn't have been introduced.

## The promise spreadsheet
For a book, keep a list:
| Promise | Set up in | Paid off in | Status |
|---------|-----------|-------------|--------|
| Iri's fear of fire | Ch. 3, p. 42 | Ch. 38 climax | open |

Unpaid promises by the end of book one go on the series spreadsheet for book two,
or get cut from book one.

## Drafter checklist
- [ ] Every new reveal: can I point at where this was set up?
- [ ] Every new setup: am I committing to pay this off?
""",
    "magic_system_template.md": """\
# Magic System Template (Sanderson's three laws + costs)

## First law
The reader's ability to predict what magic can do is proportional to how well
they understand it. Soft magic (Tolkien) is for awe; hard magic (Sanderson) is
for problem-solving.

## Second law
Limitations and costs are more interesting than powers. What can't your magic
do? What does it cost — bodily, socially, morally — to use it?

## Third law
Expand existing magic before adding new magic. Find new applications of the
established rules before introducing new abilities.

## Template fields
- **Source.** Where does the magic come from? (Innate, learned, granted, traded.)
- **Cost.** What is paid each time it's used? (Energy, blood, time, memory, sanity.)
- **Visibility.** Can non-magicians see it? Does it leave traces?
- **Rules.** Three to seven hard rules. What is impossible? What requires effort?
- **Politics.** Who benefits from the current rules of magic? Who suffers?
- **Failure modes.** What happens when it goes wrong? What does abuse look like?
- **Cultural texture.** How is magic talked about? Feared, revered, regulated, mundane?

## Drafter checklist
- [ ] Have I shown a cost being paid before a victory through magic?
- [ ] Is there a problem in this scene I can solve through clever use of
      established rules rather than new ability?
""",
    "progression_tiers_template.md": """\
# Progression / Cultivation Tier Template

A progression system needs:

1. **Named tiers.** Distinct, memorable names with internal logic.
   (e.g. Copper → Iron → Jade → Lord → Sage → Monarch → Herald → Sovereign — a
   Cradle-style sequence.)
2. **Tier thresholds.** What does a practitioner do or undergo to advance?
   A trial, a tribulation, a manifestation, a body re-forging.
3. **Capability deltas.** Concrete change between tiers: speed, durability,
   range of techniques. The reader must feel the gap.
4. **Costs and bottlenecks.** Why do most practitioners stop at tier X? Money,
   talent, resources, political access, a hidden price the masters don't disclose.
5. **Tier-coloured opposition.** The protagonist's antagonists at each tier
   feel uniquely threatening. A copper-rank thug, a jade-rank assassin, a
   lord-rank politician — each requires different protagonist skills.

## Drafter checklist
- [ ] Can the reader explain the system to a friend after this chapter?
- [ ] Did the protagonist measurably move along the system this arc?
- [ ] Is there a clear cost or bottleneck that prevents trivial advancement?
""",
    "pov_voice_audit.md": """\
# POV Voice Audit

For each POV character, the prose should sound different. Some axes to vary:

- **Diction.** Latinate vs Anglo-Saxon. Educated vs vernacular. Trade jargon vs
  layperson.
- **Sentence length.** Some POVs run long; some are clipped.
- **Filter habits.** Some notice colour, some notice money, some notice posture.
- **Metaphor pool.** Soldiers metaphorise in weapons; priests in scripture;
  cooks in spice; merchants in coin.
- **What the POV won't say.** Each POV has a topic they avoid or euphemise.

## Drafter checklist
- [ ] If I stripped the chapter heading, could I tell which POV this is from voice alone?
- [ ] What does this POV notice that no other POV would?
- [ ] What does this POV refuse to think about clearly?
""",
    "openings_and_hooks.md": """\
# Chapter Openings and Hooks

The reader can quit between chapters. They almost never quit mid-chapter.
So the first sentence of a chapter (and the last sentence of the previous one)
matter disproportionately.

## Strong opening moves
- **Concrete sensory anchor.** A specific image places the reader in the scene.
  ("The boy was burning the body when she arrived.")
- **Question in the POV's mind.** Hooks the reader to the POV's thinking.
  ("Lev hadn't planned to lie about the body. The lie surprised him.")
- **Reversal of expectation.** Opens after the obvious scene would have ended.
  ("By the time the trial started, she had already decided to confess.")

## Avoid
- Weather, unless the weather is doing something.
- A character waking up, unless waking is the inciting event.
- Long descriptions before anyone wants anything.

## Strong closing moves (chapter-end hooks)
- A decision the POV has just made that the reader knows is wrong.
- A new piece of information that recolours everything earlier in the chapter.
- A direct cliffhanger — but pay it off in the next chapter, not three later.

## Drafter checklist
- [ ] Does the chapter open with a person wanting something or noticing something specific?
- [ ] Does the last paragraph make me want to start the next chapter?
""",
    "dialogue_craft.md": """\
# Dialogue Craft

## Functions of a line of dialogue
A good line does at least two of these at once:
1. Advances the plot (information, decision, conflict).
2. Reveals character (what the speaker says, doesn't say, how they say it).
3. Reveals relationship (how they talk to *this* listener vs others).
4. Performs subtext (what's actually being negotiated under the surface).

If a line does only one of these, consider cutting or rewriting it.

## Habits to drop
- **Exposition dumps.** "As you know, my brother, our king has three sons..."
- **Said-bookisms.** "she ejaculated", "he expostulated". Use "said" — the eye
  skips it. Adverbs on said are a smell.
- **On-the-nose dialogue.** Characters announcing their feelings literally.
  ("I am very sad about my father's death.")
- **Identical voices.** Print just the dialogue lines on a page and check if you
  can tell who's speaking without tags.

## Habits to keep
- **Interruption and overlap.** People talk over each other.
- **Misunderstanding.** Two characters can have a whole scene at cross purposes.
- **Beats over tags.** Replace some "said"s with action beats that anchor the
  speaker. ("She set the cup down. 'I'm not going.'")

## Drafter checklist
- [ ] Can I tell who's speaking from voice alone?
- [ ] Is there subtext, or is everyone saying exactly what they mean?
- [ ] Are people interrupting, evading, or strategising — not just exchanging info?
""",
    "show_dont_tell.md": """\
# Showing vs Telling

A useful frame: telling is the narrator stating the conclusion the reader
should reach. Showing is giving the reader the evidence and trusting them
to draw it.

## Filter words to flag
"saw", "heard", "felt", "noticed", "realised", "thought", "wondered".
They distance the reader by one layer. Compare:

- *Telling/filtered:* She felt afraid of the man on the porch.
- *Showing:* The man on the porch hadn't moved. She measured the distance to
  the back door without turning her head.

Both have a place. Filter words in moderation set POV and pace. But a page
of "she felt / she saw / she heard" reads inert.

## When telling is right
- Compression of time. "Three weeks passed. By the end of them, he hated her."
- Establishing baseline before disruption. "Most evenings the village ate together."
- Authorial summary in omniscient or frame voice.

## Drafter checklist
- [ ] Highlight all "she felt / saw / heard / realised". Are most of them
      pulling weight, or could the sensory evidence do it?
- [ ] If I told the reader something important, did I show evidence first?
""",
    "stakes_layering.md": """\
# Stakes: Layer Three Kinds

Strong stakes are layered. Pick three for any major arc:

1. **External / plot stakes.** What happens in the world if the protagonist fails?
   (City falls, throne usurped, dungeon claims another life.)
2. **Internal / character stakes.** What does the protagonist lose internally if
   they fail? (Self-respect, faith, the version of themselves they wanted to be.)
3. **Relational stakes.** Who do they lose, or lose the trust of?
   (Lover, mentor, friend, child.)

Books that feel "small" usually have only the plot stakes. Books that haunt
have all three, and the three pull against each other so that solving one
threatens another.

## Stakes escalation
Across the book, each stake should escalate at least twice. The protagonist
who could lose the city now learns the city was always doomed; they're trying
to save the part of themselves that wanted to save the city.

## Drafter checklist
- [ ] Can I name the external, internal, and relational stakes for this scene?
- [ ] Do any two of them pull in opposite directions?
- [ ] Have stakes escalated since the previous chapter?
""",
}


# ── Build entry points ───────────────────────────────────────────────────

def build_style_cards():
    out_dir = CORPUS_DIR / "style_cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, body in STYLE_CARDS.items():
        (out_dir / fname).write_text(body, encoding="utf-8")
    print(f"  Wrote {len(STYLE_CARDS)} style cards to {out_dir}")


def build_craft_notes():
    out_dir = CORPUS_DIR / "craft"
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, body in CRAFT_NOTES.items():
        (out_dir / fname).write_text(body, encoding="utf-8")
    print(f"  Wrote {len(CRAFT_NOTES)} craft notes to {out_dir}")


def build_all(gutenberg: bool = True):
    print(f"Building corpus in {CORPUS_DIR} …")
    build_style_cards()
    build_craft_notes()
    if gutenberg:
        build_gutenberg()
    else:
        print("\nSkipped Gutenberg downloads. Run `writer corpus` to fetch.")


def list_corpus():
    if not CORPUS_DIR.exists():
        print(f"Corpus not built yet at {CORPUS_DIR}. Run: writer corpus")
        return
    for kind in ("style_cards", "craft", "gutenberg"):
        d = CORPUS_DIR / kind
        if not d.exists():
            continue
        files = sorted(d.glob("*"))
        print(f"\n{kind}/  ({len(files)} files)")
        for f in files:
            size = f.stat().st_size
            print(f"  {f.name:50s} {size:>10,} bytes")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "build":
        only_g = "--gutenberg-only" in sys.argv
        no_g   = "--no-gutenberg"  in sys.argv
        if only_g:
            build_gutenberg()
        else:
            build_all(gutenberg=not no_g)
    elif cmd == "list":
        list_corpus()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
