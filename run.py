"""Annotate Computer-Mediated Discourse with LLMs

Automates utterance-level annotation for computer-mediated communication (CMC)
data using OpenAI, Anthropic Claude, Google Gemini, or local Llama models.

1. Accepted workbook layouts

- Yusra style
    Msg# | Utterance # | Date | Time | User ID | Gender | Message
    (no Reply to_ID column)

- Soyeon style
    Msg# | Date | Category | User ID | Reply to_ID | Message
    (may contain several "Original post" rows per thread)

The loader `_load_xlsx()` normalises both layouts to a canonical dataframe with
these columns:

    Msg# | Utterance # | Date | Time | User ID | Gender | Message | Reply to_ID

Missing optional fields are filled with empty strings.

2. Prompt construction (corpus-agnostic)

- Background context: Dynamically built from conversation data
    - Detects threaded vs sequential conversation structure
    - Includes original posts that started the discussion (Msg# == 1 or Category == "Original post")
    - Uses corpus-specific background narratives (BACKGROUND_YUSRA/BACKGROUND_SOYEON)

- Local context:
    - Reply-aware (threaded): Shows parent message and reply chain based on Reply to_ID
    - Sequential fallback: Shows previous/next messages in chronological order
    - Narrative format with conversational context and user interaction patterns

- User metadata: UserID, Gender, Time, Utterance # (when available)

3. Reasoning requirement

ALL annotations require reasoning:
- Step-by-step analysis inside [REASON]…[/REASON] before the final JSON
- Minimum 20 characters of meaningful reasoning content
- Reasoning quality validation prevents empty or trivial explanations
- Failed reasoning results in retry with different seed

4. Expected model output
Reasoning followed by exactly one JSON object:

    [REASON] step-by-step analysis here [/REASON]
    [ANNOT]{"act":"<ACT>","politeness":"<POL>","meta":"< META >"}[/ANNOT]

Fields:
    act: one label from the CMC communicative-act taxonomy (18 total)
    politeness: Herring (+/-P, +/-N) or Culpeper codes with lenient dash parsing
    meta: optional meta-acts: non-bona fide, reported

5. Run-time features
- Resumable: rows with existing annotations are skipped on rerun
- Content policy handling: rows rejected by model policies are marked __FLAGGED__
- Checkpoints: output file is saved every 20 rows for progress tracking
- Comprehensive output: single CSV with all original data, annotations, reasoning, and raw API data
- No file modification: original Excel files are never modified

6. Supported models
- OpenAI: gpt-4o-*, o3-*
- Anthropic: claude-*
- Google: gemini-*
- Local: meta-llama/Llama-3.1-8B-Instruct

Environment variables required:
- OPENAI_API_KEY (for OpenAI models)
- ANTHROPIC_API_KEY (for Claude models)
- GEMINI_API_KEY (for Gemini models)

7. Output structure
Creates a single comprehensive CSV file with:
- All original columns from input Excel file
- annotation_act, annotation_politeness, annotation_meta: parsed annotations
- annotation_reasoning: extracted reasoning from model response
- raw_prompt, raw_response: complete API interaction data
- annotation_seed, annotation_timestamp: reproducibility metadata

8. Usage examples
Basic annotation:
    python run.py --xlsx data/Soyeon.xlsx --model gpt-4o-2024-08-06
    python run.py --xlsx data/Soyeon.xlsx --model claude-sonnet-4-20250514
    python run.py --xlsx data/Soyeon.xlsx --model gemini-2.5-pro-preview-06-05

Resume previous run:
    python run.py --xlsx data/Yusra.xlsx --resume previous_output.csv

Debug mode (first 10 rows):
    python run.py --xlsx data/input.xlsx --debug
"""

__author__ = "hw56@iu.edu"
__version__ = "0.5.0"
__license__ = "MIT"


import argparse
from datetime import datetime
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from tqdm import tqdm

FIXED_SEEDS = [93187, 95617, 98473, 101089, 103387]

ALLOWED_ACTS: List[str] = [
    "Accept",
    "Apologize",
    "Behave",
    "Claim",
    "Congratulate",
    "Desire (Irrealis)",
    "Desire",
    "Direct",
    "Elaborate",
    "Greet",
    "Inform",
    "Inquire",
    "Invite",
    "Manage",
    "React",
    "Reject",
    "Repair",
    "Request",
    "Thank",
]

ALLOWED_POLITENESS: List[str] = ["+P", "+N", "-P", "-N"]
ALLOWED_META: List[str] = ["non-bona fide", "reported"]
ALLOWED_META_NON_BONA_FIDE: List[str] = ['True','False']

START_TAG = "[ANNOT]"
END_TAG = "[/ANNOT]"
REASON_START = "[REASON]"
REASON_END = "[/REASON]"


BACKGROUND_YUSRA = (
    "**Background Context**: A Reddit user (JuvieThrowaw) shares that as a teenager "
    "they fatally shot their mother's abusive boyfriend after he harmed their sister, "
    "served juvenile time, and now is getting his life back on track. The user answers "
    "questions about how they feel about what happened, how it affected their "
    "relationship with their mother, sister, and stepfather, and what they are doing "
    "now."
)

BACKGROUND_SOYEON = (
    "**Background Context**: A Reddit user (CallSign_Fjor) posts in r/gaming that "
    "their friends lost interest in finishing Terraria and other games with them "
    "because the user had progressed farther, even though the user avoided using "
    "end-game gear and shared resources. The post asks why some players feel "
    "'invalidated' by someone else's faster progression."
)


def _load_xlsx(path: str) -> pd.DataFrame:
    """Load either the Yusra sheet or the Soyeon sheet and return a
    canonical DataFrame with columns

        Msg# | Utterance # | Date | Time | User ID | Gender | Message | Reply to_ID

    - Add missing optional cols (Gender, Time, Reply to_ID) as empty strings.
    - Create Utterance # when absent (running count inside each Msg# thread).
    """

    df = pd.read_excel(path, engine="openpyxl")

    # ensure Message col exists
    if "Message" not in df.columns:
        raise ValueError("Workbook must contain a 'Message' column")

    # add missing optional columns
    for col in ("Gender", "Time", "Reply to_ID"):
        if col not in df.columns:
            df[col] = ""

    # create Utterance # if absent (Yusra has it; Soyeon doesn't)
    if "Utterance #" not in df.columns:
        df["Utterance #"] = (
            df.groupby("Msg#", sort=False).cumcount() + 1
            if "Msg#" in df.columns
            else range(1, len(df) + 1)
        )

    # sanity-check required cols
    required = {"Msg#", "User ID", "Message"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Workbook missing required column(s): {missing}")

    # tidy order
    base_cols = [
        "Msg#",
        "Utterance #",
        "Date",
        "Time",
        "User ID",
        "Gender",
        "Message",
        "Reply to_ID",
    ]
    df = df[
        [c for c in base_cols if c in df.columns]
        + [c for c in df.columns if c not in base_cols]
    ]

    return df


def _format_local_context_narrative_soyeon(row_idx: int, df: pd.DataFrame) -> str:
    """
    Constructs a narrative-style local context for an utterance in the Soyeon corpus.

    Assumptions:
    - The dataframe includes a "Reply to_ID" column.
    - Each message has a unique "Msg#" identifying the utterance.
    - Replies can be chained using "Reply to_ID" to find the target's earlier messages.

    Parameters:
        row_idx (int): The row index of the utterance to annotate.
        df (pd.DataFrame): The full DataFrame containing the corpus.

    Returns:
        str: A formatted string describing the utterance, its reply target,
             earlier utterances from that user, and later replies to this utterance.
    """
    row = df.iloc[row_idx]
    user_id = row["User ID"]
    msg_id = row["Msg#"]
    reply_to = row.get("Reply to_ID")
    category = row.get("Category", "")
    msg_text = str(row["Message"]).strip()

    # start narrative
    narrative = f'We will be annotating Utterance #{row_idx} from Message #{msg_id} by {user_id}:\n"{msg_text}"\n'
    narrative += '\n**Local Context**:'
    mask = df["Msg#"].eq(msg_id)
    rows = df.loc[mask]
    msgs = rows["Message"].astype(str).fillna("").map(str.strip)
    if len(msgs) > 1:
        # Concatenate all utterances into a single message (space-separated)
        if category == "Original post":
            narrative += (
                "\nThe Utterance is part of the thread message. Read the full thread starter message for context."
            )
        else:
            full_message = " ".join(m for m in msgs if m)
            narrative += (
                f"\nThis utterance is part of the full message:\n\"{full_message}\"\n\n"
                f'You are asked only to annotate the Utterance #{row_idx}".'
            )
    if pd.notna(reply_to) and reply_to != "N/A":
        referred_df = df[(df["User ID"] == reply_to) & (df.index < row_idx)]
        if not referred_df.empty:
            if category == "Comment":
                narrative += (
                    f'\nUtterance #{row_idx} is a comment on the original post by "{reply_to}". '
                    f"Read the thread starter message for the context."
                )
            else:
                referred_df = referred_df[referred_df['Category'] != 'Original post']
                narrative += (
                    f'\nUtterance #{row_idx} is a reply to user "{reply_to}". '
                    f"The following earlier messages by {reply_to} may help contextualize the reply:"
                )
                # Group by Msg# and combine utterances into full messages
                msg_groups = referred_df.groupby("Msg#")["Message"].apply(
                    lambda x: " ".join(str(msg).strip() for msg in x)
                ).reset_index()
                
                for _, msg_row in msg_groups.iterrows():
                    narrative += (
                        f'\n- Message #{msg_row["Msg#"]}: "{msg_row["Message"]}"'
                    )

    # find the first earlier message from the same user (different message ID)
    if category != "Original post":
        same_user_earlier_mask = (df["User ID"] == user_id) & (df.index < row_idx) & (df['Reply to_ID'] == reply_to) 
        if same_user_earlier_mask.any():
            # get all earlier messages from same user and find the most recent different msg_id
            earlier_msgs = df[same_user_earlier_mask]
            different_msg_ids = earlier_msgs[earlier_msgs["Msg#"] != msg_id]["Msg#"]
            # first_earlier_msg_id=earlier_msgs["Msg#"].iloc[-1]
            if not different_msg_ids.empty:
                first_earlier_msg_id = different_msg_ids.iloc[-1]  # most recent different msg id
                # get all utterances with that msg id and combine them
                same_msg_utterances = df[df["Msg#"] == first_earlier_msg_id]["Message"].astype(str).str.strip()
                combined_earlier_msg = " ".join(same_msg_utterances)
                narrative += f"\n\nPrevious message from {user_id} in this thread:"
                narrative += f'\n- Message #{first_earlier_msg_id}: "{combined_earlier_msg}"'

        # find the first later message from the same user (different message ID)
        same_user_later_mask = (df["User ID"] == user_id) & (df.index > row_idx) & (df['Reply to_ID'] == reply_to)
        if same_user_later_mask.any():
            # get all later messages from same user and find the first different msg_id
            later_msgs = df[same_user_later_mask]
            different_msg_ids = later_msgs[later_msgs["Msg#"] != msg_id]["Msg#"]
            if not different_msg_ids.empty:
                first_later_msg_id = different_msg_ids.iloc[0]  # first different msg id
                # get all utterances with that msg id and combine them
                same_msg_utterances = df[df["Msg#"] == first_later_msg_id]["Message"].astype(str).str.strip()
                combined_later_msg = " ".join(same_msg_utterances)
                narrative += f"\n\nNext message from {user_id} in this thread:"
                narrative += f'\n- Message #{first_later_msg_id}: "{combined_later_msg}"'

    # find first replies to this utterance from other users
    later_replies = df[
        (df["Reply to_ID"] == user_id)
        & (df.index > row_idx)
        & (df["User ID"] != user_id)
    ]
    if not later_replies.empty:
        narrative += f"\n\nOther users replied to {user_id} afterward. Here are some such replies:"
        
        # Group by Msg# and combine utterances into full messages
        # Get first two unique message IDs and their combined utterances
        unique_msg_ids = later_replies["Msg#"].unique()[:2]
        reply_msg_groups = later_replies[later_replies["Msg#"].isin(unique_msg_ids)].groupby("Msg#")["Message"].apply(
            lambda x: " ".join(str(msg).strip() for msg in x)
        ).reset_index()
        
        for _, msg_row in reply_msg_groups.iterrows():
            # Get the user ID for this message
            reply_user = later_replies[later_replies["Msg#"] == msg_row["Msg#"]]["User ID"].iloc[0]
            narrative += f'\n- Message #{msg_row["Msg#"]} from {reply_user}: "{msg_row["Message"]}"'

    return narrative


def _format_local_context_narrative_yusra(row_idx: int, df: pd.DataFrame) -> str:
    """
    Constructs a narrative-style local context for an utterance in the Yusra corpus.
    For Yusra style (sequential), we use simple prev/next context.

    Parameters:
        row_idx (int): The row index of the utterance to annotate.
        df (pd.DataFrame): The full DataFrame containing the corpus.

    Returns:
        str: A formatted string describing the utterance and its context.
    """
    row = df.iloc[row_idx]
    user_id = row["User ID"]
    msg_id = row["Msg#"]
    utterance_num = row.get("Utterance #", "")
    msg_text = str(row["Message"]).strip()

    # start narrative
    narrative = f'**Local Context**: We will be annotating Utterance #{msg_id} (#{utterance_num}) from {user_id}:\n"{msg_text}"\n'

    mask = df["Msg#"].eq(msg_id)
    rows = df.loc[mask]
    msgs = rows["Message"].astype(str).fillna("").map(str.strip)
    # Concatenate all utterances into a single message (space-separated)
    full_message = " ".join(m for m in msgs if m)
    narrative += (
    f"The full message is:\n{full_message}\n\n"
    f'You are asked only to annotate the utterance "{msg_text}".'
)
    # previous message context
    if msg_id > 1:
        prev_row = df[df["Msg#"] == msg_id - 1]
        prev_text = " ".join(prev_row["Message"].astype(str).fillna("").map(str.strip))
        prev_user = prev_row["User ID"].iloc[0]
        narrative += (
            f'\nThis follows the previous message from {prev_user}:\n"{prev_text}"'
        )

    # next message context
    if msg_id < df["Msg#"].max():
        next_row = df[df["Msg#"] == msg_id + 1]
        next_text = " ".join(next_row["Message"].astype(str).fillna("").map(str.strip))
        next_user = next_row["User ID"].iloc[0]
        narrative += f'\n\nIt is followed by a message from {next_user}:\n"{next_text}"\n'
    return narrative


def _format_local_context_narrative(row_idx: int, df: pd.DataFrame) -> str:
    """
    Router function to choose the appropriate narrative formatting based on corpus type.
    """
    if "Category" in df.columns:
        return _format_local_context_narrative_soyeon(row_idx, df)
    else:
        return _format_local_context_narrative_yusra(row_idx, df)


def _get_local_context(idx: int, df: pd.DataFrame) -> Tuple[str, str]:
    """
    Return (prev_msg, next_msg) for row idx.

    - If the sheet has a non-empty 'Reply to_ID' column we fetch only the
      *parent* message (prev_msg) and leave next_msg blank, because real-world
      reply trees rarely need a "next child" for local context.
    - Otherwise fall back to simple previous / next rows (Yusra layout).
    """
    row = df.iloc[idx]

    if "Reply to_ID" in df.columns and df["Reply to_ID"].astype(str).str.strip().any():
        prev_msg = ""
        reply_to = str(row.get("Reply to_ID", "")).strip()
        if reply_to and reply_to != "N/A":
            earlier = df.iloc[:idx]
            mask = earlier["User ID"].astype(str) == reply_to
            if mask.any():
                prev_msg = earlier.loc[mask, "Message"].iloc[-1]
        return prev_msg, ""  # <-- next_msg intentionally blank

    # sequential fallback (Yusra)
    prev_msg = df.at[idx - 1, "Message"] if idx > 0 else ""
    next_msg = df.at[idx + 1, "Message"] if idx < len(df) - 1 else ""
    return prev_msg, next_msg


def _build_messages(
    system_prompt: str,
    context: Tuple[str, str, str],
    global_context: str,
    user_meta: str,
    model_tag: str,
) -> List[Dict]:
    """Compose the list of chat messages for API calls, with background + system_prompt as system role,
    and thread-aware user prompt in narrative form."""

    # Not used
    # prev_msg, target_msg, next_msg = context

    # use the pre-formatted narrative from user_meta
    narrative_intro = user_meta

    task_instruction = (
        "**Task Instruction**: You are given a single utterance from Reddit. Please read the background and surrounding context carefully, "
        "then decide on the communicative act of the target utterance, its politeness value (if clearly expressed), "
        "and any applicable meta-acts. Use the CMC Communicative Act Taxonomy developed by Herring, Das, and Penumarthy (2005), "
        "revised in 2024 by Herring and Ge-Stadnyk, to guide your annotation. For politeness and impoliteness, refer to Herring (1994) "
        "and Culpeper's (2011a) frameworks. For meta-acts such as reported perspective and non-bona fide, follow the definitions included in the taxonomy."
    )

    # ALWAYS include reasoning instructions
    # reasoning_block = (
    #     "\n**Reasoning**: Provide step-by-step analysis inside [REASON]…[/REASON] before your final answer. "
    #     "Follow the annotation procedure:"
    #     "1. **Read the target utterance carefully** in relation to the supplied context, including background story, preceding and following messages,"
    #     "2. **Pay close attention to the speaker's intent in context, not only the surface form of the message** - what is the primary communicative goal? "
    #     "3. **Consider 2-3 most plausible act options**,"
    #     "4. **Evaluate politeness/impoliteness** only if clearly expressed (not neutral interactions), "
    #     "5. **Check for meta-acts**: is this reported perspective? Is it non-bona fide speech such as sarcasm, irony, or a rhetorical question? "
    #     "Think aloud step-by-step, and select the primary communicative function, politeness (if strong enough), and meta-acts (and subtype) when appropriate."
    # )

    reasoning_block = (
        "\n**Reasoning**: Provide step-by-step analysis inside [REASON]…[/REASON] before your final answer. "
        "Follow the annotation procedure:"
        "1. **Read the target utterance carefully** in relation to the supplied context, including background story, preceding and following messages. "
        "2. **Pay close attention to the speaker's intent in context, not only the surface form of the message** - what is the primary communicative goal? "
        "3. **For the two meta-act codes:** "
        "- **Check whether there is reported perspective in the utterance.** This is often found in an embedded clause. If there is reported content and it is the most important information in the utterance in the context in which it appears, code the meta-act as \"reported\" and focus on that part when assigning an act code later. Otherwise, do not assign \"reported\" and instead focus on the main proposition when assigning the speech act later. "
        "- **Check whether the utterance is bona fide or non-bona fide.** If non-bona fide, assign the meta-act code as \"Non-bona fide\" and code the utterance for speech act as if it were sincere. "
        "4. **Consider the 2-3 most plausible act options**, and then select the primary communicative function based on the part of the utterance identified in step 3. "
        "5. **Code for politeness/impoliteness** only if clearly expressed or inferrable from the context (not neutral interactions). "
        "Think aloud step-by-step, and select the primary communicative function, politeness (if strong enough), and meta-acts (and subtype) when appropriate."
        )
    if model_tag == "o3":
        reasoning_block += (
            "\nIf you used hidden or internal reasoning anywhere, copy **all** of that "
            "reasoning verbatim inside the same [REASON]…[/REASON] block."
        )

    # always mention reasoning requirement in format block
    format_block = (
        f"\n**Output Format**: First provide your step-by-step reasoning inside {REASON_START}…{REASON_END}, "
        f"then return the annotation as one JSON object wrapped EXACTLY like:\n"
        f'{START_TAG}{{"act":"<ACT>","politeness":"<POL>","self/reported":"< META >","non-bona fide":"<NON_BONA_FIDE>"}}{END_TAG}'
    )

    return [
        {"role": "system", "content": system_prompt.strip()},
        {
            "role": "user",
            "content": f"{task_instruction}\n\n{global_context.strip()}\n\n{narrative_intro}\n{reasoning_block}\n{format_block}",
        },
    ]


def _parse_annotation(text: str) -> Dict:
    """Extract reasoning and the JSON annotation; validate all fields."""

    # REASON block (required)
    reason = ""
    if REASON_START in text and REASON_END in text:
        reason = text.split(REASON_START, 1)[1].split(REASON_END, 1)[0].strip()

    # always validate reasoning presence and quality
    if len(reason) < 20:  # Minimum meaningful reasoning length
        print('text:', text)
        raise ValueError(
            f"reasoning too short or missing (got {len(reason)} chars, need ≥20)"
        )
    # ANNOT block (required)
    if START_TAG not in text or END_TAG not in text:
        raise ValueError("annotation wrapper tags not found")

    json_str = text.split(START_TAG, 1)[1].split(END_TAG, 1)[0].strip()
    anno = json.loads(json_str)

    # 1) communicative act
    act = str(anno.get("act", "")).strip()
    if act not in ALLOWED_ACTS:
        raise ValueError(f"invalid act: {act}")

    # 2) politeness: preserve full form like "-P [Silencer]"
    raw_pol = str(anno.get("politeness", "") or "")
    raw_pol = raw_pol.replace("–", "-").replace("—", "-").strip()

    pol = raw_pol  # keep entire string

    if pol:
        base_pol = pol.split(" ", 1)[0] if " " in pol else pol
        if base_pol not in ALLOWED_POLITENESS:
            raise ValueError(f"invalid politeness: {pol}")

    # 3) meta tags_reported
    meta_field = str(anno.get("self/reported", "") or "").strip()

    clean_meta: List[str] = []
    for tag in [t.strip() for t in meta_field.split(",") if t.strip()]:
        if tag not in ALLOWED_META:
            logging.warning(f"unrecognized meta tag: {tag}")  # keep but warn
        else:
            clean_meta.append(tag)
    meta = ", ".join(clean_meta)

        # 4) meta tags_non-bona fide
    meta_field_non_bona_fide = str(anno.get("non-bona fide", "") or "").strip()

    clean_meta_non_bona_fide: List[str] = []
    for tag in [t.strip() for t in meta_field_non_bona_fide.split(",") if t.strip()]:
        if tag not in ALLOWED_META_NON_BONA_FIDE:
            logging.warning(f"unrecognized meta tag: {tag}")  # keep but warn
        else:
            clean_meta_non_bona_fide.append(tag)
    meta_non_bona_fide = ", ".join(clean_meta_non_bona_fide)

    return {"act": act, "politeness": pol, "meta": meta, "non-bona fide": meta_non_bona_fide,"reason": reason,}


def _get_model_client(model: str):
    """Initialize the appropriate client based on model name."""
    if model.startswith(("gpt-", "o3-")):
        try:
            import openai
        except ImportError:
            raise ImportError("Install with: pip install openai")
        # --- add near the top of run.py, after stdlib imports ---
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv())  # loads .env from the repo (searches upward)
        # --- end addition ---
        api_key = os.getenv("OPENAI_API_KEY")
        print('api_key:', api_key)
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable required for OpenAI models"
            )

        return openai.OpenAI(api_key=api_key), "openai"

    elif model.startswith("claude-"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install with: pip install anthropic")
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv())  # loads .env from the repo (searches upward)
        # --- end addition ---
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable required for Claude models"
            )

        return anthropic.Anthropic(api_key=api_key), "anthropic"

    elif model.startswith("gemini-"):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("Install with: pip install google-generativeai")
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv())  # loads .env from the repo (searches upward)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable required for Gemini models"
            )

        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model), "gemini"

    elif "llama" in model.lower():
        try:
            from transformers import AutoTokenizer
            from vllm import LLM, SamplingParams
        except ImportError:
            raise ImportError("Install with: pip install transformers vllm")

        tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
        llm = LLM(model=model, dtype="bfloat16")
        return (llm, tokenizer), "llama"

    else:
        raise ValueError(f"Unsupported model: {model}")


def extract_gemini_text(resp) -> str:
    """Return first textual Part from a Gemini response or ''."""
    for cand in getattr(resp, "candidates", []) or []:
        for part in cand.content.parts:
            if getattr(part, "text", ""):
                return part.text.strip()
    return ""


def _annotate_row(
    row_idx: int,
    df: pd.DataFrame,
    sys_prompt: str,
    model: str,
    client,
    client_type: str,
    max_tries: int,
    global_context: str,
    user_meta: str,
) -> Tuple[Dict, List[Dict]]:
    """Annotate one DataFrame row, retrying with incremental seeds."""
    raw_records: List[Dict] = []

    prev_msg, next_msg = _get_local_context(row_idx, df)
    targ_msg = df.at[row_idx, "Message"]

    base_seed = FIXED_SEEDS[0]

    for attempt in range(max_tries):
        seed = base_seed + attempt
        messages = _build_messages(
            sys_prompt,
            (prev_msg, targ_msg, next_msg),
            global_context,
            user_meta,
            model.split("-")[0] if "-" in model else model,
        )

        try:
            if client_type == "openai":
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.6,
                    top_p=0.9,
                    max_tokens=10240,
                    seed=seed,
                )
                content = resp.choices[0].message.content
                ts = resp.created

                if not content or len(content.strip()) == 0:
                    raise RuntimeError(
                        f"OpenAI: empty output for row {row_idx} seed {seed} — retrying"
                    )

            elif client_type == "anthropic":
                system_content = messages[0]["content"]
                user_content = messages[1]["content"]

                resp = client.messages.create(
                    model=model,
                    max_tokens=10240,
                    temperature=0,
                    top_p=1,
                    system=system_content,
                    messages=[{"role": "user", "content": user_content}],
                )
                content = resp.content[0].text
                ts = time.time()

                if not content or len(content.strip()) == 0:
                    raise RuntimeError(
                        f"Claude: empty output for row {row_idx} seed {seed} — retrying"
                    )

            elif client_type == "gemini":
                prompt_text = f"{messages[0]['content']}\n\n{messages[1]['content']}"
                # change the temperature to 0 for Gemini
                resp = client.generate_content(
                    prompt_text,
                    generation_config={
                        "temperature": 0,
                        "top_p": 1,
                        "max_output_tokens": 10240,
                    },
                )

                reply_text = extract_gemini_text(resp)

                if not reply_text:
                    raise RuntimeError(
                        f"Gemini: empty response for row {row_idx} seed {seed} — retrying"
                    )

                content = reply_text
                ts = time.time()

            elif client_type == "llama":
                llm, tokenizer = client
                from vllm import SamplingParams

                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                out = llm.generate(
                    [prompt],
                    sampling_params=SamplingParams(
                        temperature=0.6,
                        top_p=0.9,
                        max_tokens=1024,
                        seed=seed,
                    ),
                )[0].outputs[0]
                content = out.text
                ts = time.time()

                if not content or len(content.strip()) == 0:
                    raise RuntimeError(
                        f"LLaMA: empty output for row {row_idx} seed {seed} — retrying"
                    )

        except Exception as e:
            if "policy" in str(e).lower() or "safety" in str(e).lower():
                logging.warning(
                    f"Row {row_idx} seed {seed} flagged by policy; skipping."
                )
                raise RuntimeError("policy_flagged")
            else:
                logging.warning(f"Row {row_idx} seed {seed} API error: {e}")
                time.sleep(2**attempt)
                continue

        raw_records.append(
            {
                "row_idx": row_idx,
                "seed": seed,
                "prompt": json.dumps(messages, ensure_ascii=False),
                "response": content,
                "timestamp": ts,
            }
        )

        try:
            anno = _parse_annotation(content)
            anno.update({"row_idx": row_idx, "seed": seed})
            return anno, raw_records

        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"Row {row_idx} seed {seed} parse error: {e}")
            time.sleep(2**attempt)

    raise RuntimeError(f"row {row_idx}: parse failed after {max_tries} tries")


def _create_output_dataframe(
    df: pd.DataFrame, annotations: List[Dict], raw_records: List[Dict]
) -> pd.DataFrame:
    """Create comprehensive output dataframe with original data + annotations + raw data."""

    # start with original data
    output_df = df.copy()

    # add annotation columns
    output_df["annotation_act"] = ""
    output_df["annotation_politeness"] = ""
    output_df["annotation_meta"] = ""
    output_df['annotation_NBF'] = ""
    output_df["annotation_reasoning"] = ""
    output_df["raw_prompt"] = ""
    output_df["raw_response"] = ""
    output_df["annotation_seed"] = ""
    output_df["annotation_timestamp"] = ""

    # fill in annotations
    for anno in annotations:
        row_idx = anno["row_idx"]
        output_df.at[row_idx, "annotation_act"] = anno.get("act", "")
        output_df.at[row_idx, "annotation_politeness"] = anno.get("politeness", "")
        output_df.at[row_idx, "annotation_meta"] = anno.get("meta", "")
        output_df.at[row_idx, "annotation_NBF"] = anno.get("non-bona fide", "")
        output_df.at[row_idx, "annotation_reasoning"] = anno.get("reason", "")
        output_df.at[row_idx, "annotation_seed"] = anno.get("seed", "")

    # fill in raw data (use the successful attempt)
    for raw in raw_records:
        row_idx = raw["row_idx"]
        seed = raw["seed"]
        # Only use the raw data from successful annotations
        if any(a["row_idx"] == row_idx and a["seed"] == seed for a in annotations):
            output_df.at[row_idx, "raw_prompt"] = raw["prompt"]
            output_df.at[row_idx, "raw_response"] = raw["response"]
            output_df.at[row_idx, "annotation_timestamp"] = raw["timestamp"]

    return output_df


def main() -> None:
    """Entry point: load data, annotate rows, and save comprehensive output file."""

    # CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default="data/Yusra.xlsx", help="Input Excel file")
    parser.add_argument(
        "--output_dir",
        default="annotations",
        help="Output dir name (auto-generated file names)",
    )
    parser.add_argument(
        "--model", default="gpt-4o-2024-08-06", help="Model to use for annotation"
    )
    parser.add_argument(
        "--max_tries", type=int, default=20, help="Maximum retry attempts"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Debug mode (first 10 rows only)"
    )
    parser.add_argument("--resume", help="Resume from existing output file")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO
    )
    logging.info("Starting annotation run")

    # load & normalize workbook
    df = _load_xlsx(args.xlsx)

    # determine output filename
    input_stem = Path(args.xlsx).stem
    model_name = args.model.replace("/", "_").replace("-", "_")
    date = datetime.now().strftime("%m-%d_%H-%M-%S")
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = f"{args.output_dir}/{input_stem}_annotated_{model_name}_{date}.csv"

    # initialize tracking
    annotations = []
    all_raw_records = []
    completed_rows = set()

    # resume from existing file if specified
    if args.resume and Path(args.resume).exists():
        logging.info(f"Resuming from {args.resume}")
        resume_df = pd.read_csv(args.resume)
        for idx, row in resume_df.iterrows():
            # check for complete annotation: must have act, reasoning, and raw data
            has_act = row.get("annotation_act") and str(
                row.get("annotation_act")
            ).strip() not in ("", "__FAILED__", "__FLAGGED__")
            has_reasoning = (
                row.get("annotation_reasoning")
                and str(row.get("annotation_reasoning")).strip()
            )
            has_raw_data = (
                row.get("raw_response") and str(row.get("raw_response")).strip()
            )

            if has_act and has_reasoning and has_raw_data:
                annotations.append(
                    {
                        "row_idx": idx,
                        "act": row["annotation_act"],
                        "politeness": row.get("annotation_politeness", ""),
                        "meta": row.get("annotation_meta", ""),
                        "reason": row.get("annotation_reasoning", ""),
                        "seed": row.get("annotation_seed", ""),
                    }
                )
                # also restore the raw records for complete data integrity
                if row.get("raw_prompt") and row.get("raw_response"):
                    all_raw_records.append(
                        {
                            "row_idx": idx,
                            "seed": row.get("annotation_seed", ""),
                            "prompt": row["raw_prompt"],
                            "response": row["raw_response"],
                            "timestamp": row.get("annotation_timestamp", time.time()),
                        }
                    )
                completed_rows.add(idx)
            elif str(row.get("annotation_act")).strip() in (
                "__FAILED__",
                "__FLAGGED__",
            ):
                # also skip previously failed/flagged rows
                annotations.append(
                    {
                        "row_idx": idx,
                        "act": row["annotation_act"],
                        "politeness": "",
                        "meta": "",
                        "reason": "",
                        "seed": row.get("annotation_seed", ""),
                    }
                )
                completed_rows.add(idx)

        logging.info(f"Resumed {len(completed_rows)} previously completed rows")

    # build dynamic global context
    if "Category" in df.columns:  # Soyeon layout
        thread_summary = BACKGROUND_SOYEON
        # Group original post utterances by Msg# to form complete messages
        original_post_df = df[df["Category"] == "Original post"]
        original_posts = []
        for msg_id in original_post_df["Msg#"].unique():
            msg_utterances = original_post_df[original_post_df["Msg#"] == msg_id]["Message"].dropna()
            complete_message = " ".join(msg_utterances.astype(str))
            original_posts.append(complete_message)
    else:  # Yusra layout
        thread_summary = BACKGROUND_YUSRA
        # Group utterances by Msg# to form complete messages
        msg_1_df = df[df["Msg#"] == 1]
        original_posts = []
        for msg_id in msg_1_df["Msg#"].unique():
            msg_utterances = msg_1_df[msg_1_df["Msg#"] == msg_id]["Message"].dropna()
            complete_message = " ".join(msg_utterances.astype(str))
            original_posts.append(complete_message)

    dynamic_global_context = "\n\n".join(
        [
            thread_summary,
            "Thread starter messages:\n" + "\n".join(f"- {m}" for m in original_posts),
        ]
    )

    # initialize model client
    client, client_type = _get_model_client(args.model)

    # load system prompt
    system_prompt_path = Path("system_prompt_final.md")
    if not system_prompt_path.exists():
        raise ValueError("System prompt not specified.")
    else:
        system_prompt = system_prompt_path.read_text(encoding="utf-8")

    # determine rows to annotate
    todo_idx = [idx for idx in df.index if idx not in completed_rows]
    if args.debug:
        todo_idx = todo_idx[0:10]
        logging.info("Debug mode: first 10 only")
        debug_dir = os.path.join(args.output_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        output_path = os.path.join(debug_dir, os.path.basename(output_path))
        output_path = output_path.replace(".csv", "_debug.csv")
        logging.info(f"Debug output will be saved to: {output_path}")

    pbar = tqdm(todo_idx, desc="Annotating", unit="row")

    # main annotation loop
    for idx in pbar:
        user_meta = _format_local_context_narrative(idx, df)

        try:
            # print('system_prompt:', system_prompt)
            anno, raws = _annotate_row(
                idx,
                df,
                system_prompt,
                args.model,
                client,
                client_type,
                args.max_tries,
                global_context=dynamic_global_context,
                user_meta=user_meta,
            )

            annotations.append(anno)
            all_raw_records.extend(raws)
            logging.info(f"Annotated row {idx}: {anno['act']}")

            # debug printout: print last generation
            if args.debug:
                print("\n--- Generation for row", idx, "---")
                try:
                    # system_prompt = json.loads(raws[-1]["prompt"])[0]["content"]
                    user_prompt = json.loads(raws[-1]["prompt"])[1]["content"]
                except Exception:
                    user_prompt = "[[ Could not parse user prompt ]]"
                # print("System Prompt:\n", system_prompt)
                print("Prompt:\n", user_prompt)
                print("\nResponse:\n", raws[-1]["response"])
                print("--- end of generation ---\n")

        except RuntimeError as exc:
            flag = "__FLAGGED__" if str(exc) == "policy_flagged" else "__FAILED__"
            logging.error(f"Row {idx}: {exc}")

            failed_anno = {
                "row_idx": idx,
                "act": flag,
                "politeness": "",
                "meta": "",
                "reason": "",
                "seed": FIXED_SEEDS[0],
            }
            annotations.append(failed_anno)

        # periodic save (every 20 rows)
        if len(annotations) % 20 == 0:
            output_df = _create_output_dataframe(df, annotations, all_raw_records)
            output_df.to_csv(output_path, index=False, encoding="utf-8-sig")
            logging.info(f"Checkpoint saved: {len(annotations)} rows completed")

    # final save
    output_df = _create_output_dataframe(df, annotations, all_raw_records)
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    # summary statistics
    total_annotations = len(
        [a for a in annotations if a["act"] not in ("__FAILED__", "__FLAGGED__")]
    )
    failed_count = len([a for a in annotations if a["act"] == "__FAILED__"])
    flagged_count = len([a for a in annotations if a["act"] == "__FLAGGED__"])

    logging.info(f"Annotation complete!")
    logging.info(f"Output saved to: {output_path}")
    logging.info(f"Total annotations: {total_annotations}")
    logging.info(f"Failed: {failed_count}")
    logging.info(f"Flagged: {flagged_count}")
    logging.info(f"Success rate: {total_annotations / len(annotations) * 100:.1f}%")


if __name__ == "__main__":
    main()
