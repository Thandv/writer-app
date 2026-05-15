# Publishing on Amazon KDP

This document is informational, not legal advice. Policies change — verify
against the current Amazon KDP and US Copyright Office documents before
relying on anything here.

## KDP's rules in plain English

Amazon KDP distinguishes two categories at upload (since September 2023):

- **AI-generated content** — text/images/translations *created* by an AI
  tool, even if you then refined it. **Must be disclosed.**
- **AI-assisted content** — AI used to *edit, polish, or check* content you
  wrote yourself. **No disclosure required.**

Books produced with writer-app fall in the **AI-generated** category. You
must answer "yes" on the disclosure form. This applies even after running
the humanizer — the humanizer reduces detectable AI tells in the prose, but
the prose was still AI-generated. KDP's disclosure question is about who
created the text, not how detectable it is.

### Practical details

- Disclosure is **internal to Amazon**. It does not appear on your book's
  product page. Readers cannot see it from the listing.
- Failing to disclose is a Terms of Service violation. Risk: account
  suspension, lost royalties, removed titles.
- Disclosure does **not** prevent you from publishing or from earning
  royalties.
- KDP currently limits new accounts to **3 titles per day** to slow AI
  floods. Plan multi-book series uploads accordingly.

Run `writer disclosure ~/books/<slug>` to get the exact answer text and a
copy in `KDP_DISCLOSURE.md`.

## Copyright (US)

Current US Copyright Office position (post-*Zarya of the Dawn*, 2023, and
subsequent USCO guidance):

| Element | Copyrightable? |
|---|---|
| Plot, story arcs, scene-level decisions where author-authored | **Yes — your IP** |
| World, geography, history, cultures | **Yes** |
| Magic / power system, rules, costs | **Yes** |
| Named characters, their drives, wounds, relationships | **Yes** |
| Editorial selection and arrangement of AI-drafted text | **Yes — compilation/editorial authorship** |
| The AI-generated prose itself | **No** — public domain in the US |
| Prose you substantially revised after AI generation | **Yes** — to the extent of your contribution |

### Implications for defending your work

- If someone steals your plot, characters, world, or magic system → they
  infringe your copyright. You can act.
- If someone copies AI-generated paragraphs verbatim → harder claim;
  prose itself is not protected. They'd still infringe your *compilation*
  if they copied the whole book.
- The more you revise, the stronger your position. A line-edited chapter
  is much more defensible than an unedited one.

### Optional: USCO registration (~$45)

For a commercial novel it's worth registering. On the form, describe
authorship as: "Original plot, characters, world, and magic system. Prose
drafted with AI assistance and selected/arranged by the author." The USCO
has specific Q&A on AI-assisted works.

`PROVENANCE.md` (auto-generated per book) is your audit trail: which
chapters were drafted by which model on which date, how many revision
iterations, AI-tell scores before and after humanizing, and which chapters
have user-revised overrides.

## Self-pub checklist

1. **Authorship paper trail** — keep dated versions of the world bible,
   characters, plot notes *before* the pipeline ran. Git is fine.
2. **Revision trail** — when you save user revisions in
   `book-NN/revisions/chapter-NN.md`, the date of edit and your changes
   are preserved.
3. **Real revision pass** — at minimum, read every chapter; better, line-
   edit. Each substantive edit increases your copyright position.
4. **Cover** — hire a human or generate with an AI tool you disclose.
   writer-app does not produce covers.
5. **Optional: human copy-editor** for a final pass (~$300–800 via
   Reedsy etc.). Their edits are further human authorship in the work.
6. **KDP submission**:
   - US tax info (SSN or ITIN; non-US authors fill W-8BEN)
   - Disclose AI-generated text — answer **yes**, per `KDP_DISCLOSURE.md`
   - Disclose AI cover if applicable
   - Price, KU enrolment, categories, keywords
   - Optional pen name for separation from your real name
7. **Optional: USCO registration** with the AI-assistance description.
8. **Marketing** — AI-disclosed novels can do well in progression-fantasy
   and litRPG niches with strong cover, clear premise, mailing list, and
   Amazon Ads. They tend to face hostility on r/fantasy and Goodreads
   when announced as AI-generated. A pen name limits reputational risk.

## What sells (honest take)

The pipeline produces a *draft*. What sells:

- **Premise** — clear, distinctive, niche-aware
- **Cover** — professional or near-professional
- **First chapter** — earns the next click
- **Series promise** — readers commit when they trust there's a book 2
- **Active marketing** — ads, mailing list, ARC team

Pipeline-quality alone is usually not enough. A minimum-revision approach
limits but does not eliminate commercial potential; serious revision
multiplies it.

## What it can't help with

- Whether your specific story is commercially viable in your niche
- KDP audits / account reviews — those depend on your behaviour over time,
  not the tool used
- Reader perception of AI-generated fiction — varies wildly by community
- Legal advice on edge cases — consult a lawyer for anything specific

## Disclosure summary

- KDP: **yes, AI-generated text**
- USCO registration: describe AI-assisted authorship; disclaim purely AI
  portions or describe extent of human revision
- Marketing copy / book description: **disclosure not legally required**
  in most jurisdictions, but increasingly expected by readers in some
  communities (your call)
