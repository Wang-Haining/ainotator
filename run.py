"""Annotate CMC utterances with AI

Reads an Excel file (one utterance per row), sends a 3-line context
(previous, target, next) to the specified OpenAI model, retries on parse
failure, and writes both raw and cleaned annotations to `annotations/seed_{SEED}/`.

Features
--------
• Resumable: rows already carrying an `act` label are skipped.
• Debug mode (`--debug`): process only the first 10 unannotated rows.
• Chain-of-thought toggle (`--cot`): keep model reasoning inside
  `[REASON]…[/REASON]` (saved in raw log, ignored for parsing).
• Audit trail: every prompt/response pair logged to Parquet.

Usage:
    python run.py
"""

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
    global_context: str = "",  # NEW: optional global context
) -> List[Dict]:
    """Compose the list of chat messages for OpenAI."""
    prev_msg, target_msg, next_msg = context
    user_block = (
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
        f"{START_TAG}{{\"act\":\"<ACT>\","
        "\"politeness\":\"<POL>\",\"meta\":\"<META>\"}}{END_TAG}"
    )

    system_block = (
        (global_context.strip() + "\n\n" if global_context else "") + system_prompt
    )

    return [
        {"role": "system", "content": system_block},
        {"role": "user", "content": user_block + reasoning_block + format_block},
    ]


def _parse_annotation(text: str) -> Dict:
    """Extract and validate the JSON annotation from model output."""
    if START_TAG not in text or END_TAG not in text:
        raise ValueError("wrapper tags not found")
    json_str = text.split(START_TAG, 1)[1].split(END_TAG, 1)[0].strip()
    anno = json.loads(json_str)

    act = anno.get("act")
    pol = anno.get("politeness")
    meta = anno.get("meta", "")

    if act not in ALLOWED_ACTS:
        raise ValueError(f"invalid act: {act}")
    if pol and not any(pol.startswith(p) for p in ALLOWED_POLITENESS):
        raise ValueError(f"invalid politeness: {pol}")
    if meta and meta not in ALLOWED_META:
        raise ValueError(f"invalid meta: {meta}")
    return anno


def _annotate_row(
    row_idx: int,
    df: pd.DataFrame,
    sys_prompt: str,
    model: str,
    max_tries: int,
    include_cot: bool,
    global_context: str,
) -> Tuple[Dict, List[Dict]]:
    """Annotate a single DataFrame row, retrying with FIXED_SEEDS."""
    raw_records: List[Dict] = []
    prev_msg = df.iloc[row_idx - 1]["Message"] if row_idx > 0 else ""
    targ_msg = df.iloc[row_idx]["Message"]
    next_msg = df.iloc[row_idx + 1]["Message"] if row_idx < len(df) - 1 else ""

    base_seed = FIXED_SEEDS[0]  # fixme
    for attempt in range(max_tries):
        seed = base_seed + attempt
        messages = _build_messages(
            sys_prompt, (prev_msg, targ_msg, next_msg), include_cot, global_context
        )
        resp = openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            top_p=0.95,
            seed=seed,
        )
        content = resp.choices[0].message.content
        raw_records.append(
            {
                "row_idx": row_idx,
                "seed": seed,
                "prompt": json.dumps(messages, ensure_ascii=False),
                "response": content,
                "timestamp": resp.created,
            }
        )
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
    parser.add_argument(
        "--xlsx",
        default="data/Yusra_politeness.sch.copy.xlsx",
        help="input Excel file",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-2024-08-06",
        help="OpenAI model name",
    )
    parser.add_argument(
        "--max_tries",
        type=int,
        default=5,
        help="maximum retries per utterance",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="process only first 10 unannotated rows",
    )
    parser.add_argument(
        "--cot",
        action="store_true",
        help="include chain-of-thought reasoning in output",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=logging.INFO,
    )
    logging.info("Starting annotation run")

    primary_seed = FIXED_SEEDS[0]
    cot_suffix = "_cot" if args.cot else ""
    out_dir = Path("annotations") / f"seed_{primary_seed}{cot_suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Output directory: {out_dir}")

    df = pd.read_excel(args.xlsx, engine="openpyxl")
    for col in ("act", "politeness", "meta"):
        if col not in df.columns:
            df[col] = ""

    todo_idx = df.index[~df["act"].astype(bool)]
    if args.debug:
        todo_idx = todo_idx[:10]
        logging.info("Debug mode: limiting to first 10 items")

    with open("system_prompt.txt", encoding="utf-8") as fh:
        system_prompt = fh.read()

    clean_rows, raw_rows = [], []
    pbar = tqdm(todo_idx, desc="Annotating", unit="row")
    for idx in pbar:
        try:
            anno, raws = _annotate_row(
                idx,
                df,
                system_prompt,
                args.model,
                args.max_tries,
                include_cot=args.cot,
                global_context=global_context,
            )

            clean_rows.append(anno)
            raw_rows.extend(raws)
            df.loc[idx, ["act", "politeness", "meta"]] = (
                anno["act"],
                anno["politeness"],
                anno["meta"],
            )
            logging.info(f"Annotated row {idx}")
        except RuntimeError as exc:
            logging.error(exc)
        pbar.update(0)  # refresh description

    pd.DataFrame(raw_rows).to_csv(out_dir / "annot_raw.csv", index=False)
    pd.DataFrame(clean_rows).to_csv(out_dir / "annot_clean.csv", index=False)
    df.to_csv(out_dir / "annot_seq.csv", index=False)

    logging.info("Annotation run complete")


if __name__ == "__main__":
    main()
