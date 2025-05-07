"""Annotate CMC utterances with AI

This script automates utterance-level annotation for computer-mediated communication
(CMC) research using OpenAI chat models.

It reads an Excel file where each row is one utterance with associated metadata
(User ID, Gender, Time, Utterance #, Msg#), constructs a rich prompt including:
 0. Background: a Reddit user (“JuvieThrowaw”) recounts a premeditated...
 1. Thread starter: all thread-starter posts (Msg# == 1) to anchor the conversation,
 2. User metadata: speaker identity and timing for each target utterance,
 3. Local context: the immediate previous, target, and next messages.

Each prompt optionally includes chain-of-thought reasoning inside `[REASON]…[/REASON]`
when `--cot` is enabled, and finally requests a structured JSON annotation wrapped in
`[ANNOT]…[/ANNOT]`.

What does a prompt look like:
```SYSTEM:
<contents of system_prompt.md>

USER:
Background: A Reddit user (“JuvieThrowaw”) shares that as a teenager they fatally shot
their mother's abusive boyfriend after he harmed their sister...

Thread starter: My mom was as in an abusive relationship with her boyfriend...

[META] UserID: X, Gender: Y, Time: T, Utterance#: N
[PREV] …
[TARGET] …
[NEXT] …

Think step-by-step inside [REASON]…[/REASON] before the answer.   # only if --cot
Return the annotation as one JSON object wrapped EXACTLY like:
[ANNOT]{"act":"<ACT>","politeness":"<POL>","meta":"<META>"}[/ANNOT]
```

Annotations include three fields:
 - `act`: one label from the CMC communicative-act taxonomy,
 - `politeness`: Herring (1994) politeness or Culpeper (2011a) impoliteness codes,
 - `meta`: optional meta-acts (`non-bona fide` or `reported`).

Key features:
 - **Resumable**: skips rows already annotated (uses `act` column),
 - **Debug mode** (`--debug`): process only the first 10 unannotated rows,
 - **CoT mode** (`--cot`): include model reasoning for transparency,
 - **Seeded reproducibility**: fixed seed plus incremental offsets,
 - **Incremental audit**: writes raw prompts, responses, and cleaned annotations to CSV
    as it runs.

Usage:
    python run.py [--xlsx path/to/file.xlsx] [--model MODEL] [--max_tries N] [--debug]
    [--cot]
"""

__author__ = "The AInotator authors"
__version__ = "0.0.3"
__license__ = "MIT"


import argparse
import json
import time
from pathlib import Path
import logging
from typing import Dict, List, Tuple

import openai
import pandas as pd
from tqdm import tqdm


FIXED_SEEDS = [93187, 95617, 98473, 101089, 103387]

ALLOWED_ACTS: List[str] = [
    "Accept", "Apologize", "Behave", "Claim", "Congratulate", "Desire",
    "Direct", "Elaborate", "Greet", "Inform", "Inquire", "Invite", "Manage",
    "React", "Reject", "Repair", "Request", "Thank",
]
ALLOWED_POLITENESS: List[str] = ["+P", "+N", "-P", "-N"]
ALLOWED_META: List[str] = ["non-bona fide", "reported"]

START_TAG = "[ANNOT]"
END_TAG = "[/ANNOT]"
REASON_START = "[REASON]"
REASON_END = "[/REASON]"


global_context = (
    "A Reddit user (JuvieThrowaw) recounts being sentenced to juvenile detention as a "
    "teenager after killing his mother's abusive boyfriend. The act was premeditated: "
    "he waited at the boyfriend's house after the boyfriend had harmed his sister. "
    "Years later, the user is unsure how much of this past to disclose to new close "
    "friends and partners."
)


def _build_messages(
    system_prompt: str,
    context: Tuple[str, str, str],
    include_cot: bool,
    global_context: str,
    user_meta: str,
) -> List[Dict]:
    """Compose the list of chat messages for OpenAI, including global context and user
    metadata."""
    prev_msg, target_msg, next_msg = context

    # prepend user metadata (plain text lines)
    user_block = (
        f"{user_meta}"
        f"[PREV] {prev_msg or '<NONE>'}\n"
        f"[TARGET] {target_msg}\n"
        f"[NEXT] {next_msg or '<NONE>'}\n"
    )

    reasoning_block = (
        "\nThink step-by-step inside [REASON]…[/REASON] before the answer."
        if include_cot else ""
    )

    format_block = (
        "\nReturn the annotation as one JSON object wrapped EXACTLY like:\n"
        f"{START_TAG}{{\"act\":\"<ACT>\",\"politeness\":\"<POL>\",\"meta\":\"<META>\"}}{END_TAG}"
    )

    system_block = f"{global_context.strip()}\n\n{system_prompt}"

    return [
        {"role": "system", "content": system_block},
        {"role": "user",   "content": user_block + reasoning_block + format_block},
    ]


def _parse_annotation(text: str) -> Dict:
    """Extract reasoning (optional) and the JSON annotation; validate all fields."""

    # -------- REASON block (optional) --------
    reason = ""
    if REASON_START in text and REASON_END in text:
        reason = text.split(REASON_START, 1)[1].split(REASON_END, 1)[0].strip()

    # -------- ANNOT block (required) ---------
    if START_TAG not in text or END_TAG not in text:
        raise ValueError("wrapper tags not found")

    json_str = text.split(START_TAG, 1)[1].split(END_TAG, 1)[0].strip()
    anno = json.loads(json_str)

    # ---------- 1) communicative act ----------
    act = str(anno.get("act", "")).strip()
    if act not in ALLOWED_ACTS:
        raise ValueError(f"invalid act: {act}")

    # ---------- 2) politeness (+ optional subtype) ----------
    raw_pol = str(anno.get("politeness", "") or "")
    raw_pol = raw_pol.replace("–", "-").replace("—", "-").strip()

    meta_field = str(anno.get("meta", "") or "").strip()  # safe default ""

    if raw_pol.lower() == "none":
        pol, meta_from_pol = "", ""
    else:
        if "[" in raw_pol and "]" in raw_pol:
            base, subtype = raw_pol.split("[", 1)
            pol = base.strip()
            meta_from_pol = subtype.rstrip("]").strip()
        else:
            pol = raw_pol
            meta_from_pol = ""

    if pol and pol not in ALLOWED_POLITENESS:
        raise ValueError(f"invalid politeness: {pol}")

    # ---------- 3) meta tags ----------
    combined_meta = ", ".join(filter(None, [meta_field, meta_from_pol]))
    clean_meta: List[str] = []
    for tag in [t.strip() for t in combined_meta.split(",") if t.strip()]:
        if tag not in ALLOWED_META:
            logging.warning(f"unrecognized meta tag: {tag}")  # keep but warn
        else:
            clean_meta.append(tag)
    meta = ", ".join(clean_meta)

    return {"act": act, "politeness": pol, "meta": meta, "reason": reason}



def _annotate_row(
    row_idx: int,
    df: pd.DataFrame,
    sys_prompt: str,
    model: str,
    max_tries: int,
    include_cot: bool,
    global_context: str,
    user_meta: str,
) -> Tuple[Dict, List[Dict]]:
    """Annotate a single DataFrame row, retrying with seeded offsets."""
    raw_records: List[Dict] = []
    prev_msg = df.at[row_idx - 1, "Message"] if row_idx > 0 else ""
    targ_msg = df.at[row_idx,     "Message"]
    next_msg = df.at[row_idx + 1, "Message"] if row_idx < len(df) - 1 else ""

    base_seed = FIXED_SEEDS[0]
    for attempt in range(max_tries):
        seed = base_seed + attempt
        messages = _build_messages(
            sys_prompt,
            (prev_msg, targ_msg, next_msg),
            include_cot,
            global_context,
            user_meta,
        )
        resp = openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            top_p=0.95,
            seed=seed,
        )
        content = resp.choices[0].message.content
        raw_records.append({
            "row_idx":    row_idx,
            "seed":       seed,
            "prompt":     json.dumps(messages, ensure_ascii=False),
            "response":   content,
            "timestamp":  resp.created,
        })
        try:
            anno = _parse_annotation(content)
            anno.update({"row_idx": row_idx, "seed": seed})
            return anno, raw_records
        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"Row {row_idx} seed {seed} parse error: {e}")
            time.sleep(2 ** attempt)

    raise RuntimeError(f"row {row_idx}: parse failed after {max_tries} tries")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx",      default="data/Yusra_politeness.sch.copy.xlsx")
    parser.add_argument("--model",     default="gpt-4o-2024-08-06")
    parser.add_argument("--max_tries", type=int, default=20)
    parser.add_argument("--debug",     action="store_true")
    parser.add_argument("--cot",       action="store_true")
    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)
    logging.info("Starting annotation run")

    # load data once
    df = pd.read_excel(args.xlsx, engine="openpyxl")

    # build dynamic global context: a brief background + all Msg# == 1 posts
    first_posts = df.loc[df["Msg#"] == 1, "Message"].dropna().tolist()
    thread_summary = (
        "Background: A Reddit user (“JuvieThrowaw”) shares that as a teenager they "
        "fatally shot their mother's abusive boyfriend after he harmed their sister, "
        "served juvenile time, and now struggles with whether to disclose this past "
        "to new friends and partners."
    )
    dynamic_global_context = "\n\n".join([
        thread_summary,
        "Thread starter messages:\n" + "\n".join(f"- {m}" for m in first_posts)
    ])

    primary_seed = FIXED_SEEDS[0]
    cot_suffix = "_cot" if args.cot else ""
    out_dir = Path("annotations") / f"seed_{primary_seed}{cot_suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Output directory: {out_dir}")

    # initialize annotation columns if missing
    for col in ("act", "politeness", "meta"):
        if col not in df.columns:
            df[col] = ""

    # determine which rows to process
    todo_idx = df.index[~df["act"].astype(bool)]
    if args.debug:
        todo_idx = todo_idx[:10]
        logging.info("Debug mode: first 10 only")

    system_prompt = Path("system_prompt.md").read_text(encoding="utf-8")
    pbar = tqdm(todo_idx, desc="Annotating", unit="row")

    for idx in pbar:
        row = df.iloc[idx]
        user_meta = (
            f"UserID: {row['User ID']}, "
            f"Gender: {row['Gender']}, "
            f"Time: {row['Time']}, "
            f"Utterance#: {row['Utterance #']}\n"
        )
        try:
            anno, raws = _annotate_row(
                idx, df, system_prompt, args.model, args.max_tries,
                include_cot=args.cot, global_context=dynamic_global_context,
                user_meta=user_meta,
            )
            # assign three columns in one go
            df.loc[idx, ["act", "politeness", "meta"]] = [
                anno["act"], anno["politeness"], anno["meta"]
            ]

            pd.DataFrame([anno]).to_csv(
                out_dir / "annot_clean.csv",
                mode="a",
                header=not (out_dir / "annot_clean.csv").exists(),
                index=False
            )
            pd.DataFrame(raws).to_csv(
                out_dir / "annot_raw.csv",
                mode="a", header=not (out_dir / "annot_raw.csv").exists(),
                index=False
            )
            df.iloc[[idx]].to_csv(
                out_dir / "annot_seq.csv",
                mode="a", header=not (out_dir / "annot_seq.csv").exists(),
                index=False
            )

            logging.info(f"Annotated row {idx}")
        except RuntimeError as exc:
            logging.error(exc)
            # mark failed row to preserve row alignment
            df.loc[idx, ["act", "politeness", "meta"]] = ["__FAILED__", "", ""]
            df.iloc[[idx]].to_csv(
                out_dir / "annot_seq.csv",
                mode="a", header=not (out_dir / "annot_seq.csv").exists(),
                index=False
            )

    logging.info("Annotation run complete")


if __name__ == '__main__':
    main()
