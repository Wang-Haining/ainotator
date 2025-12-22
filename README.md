# 🤖 CMD-AInotator: Computer-Mediated Discourse Annotation (CMDA) with LLMs

Can LLMs understand what is meant, not just what is said?
**CMD-AInotator** puts this question to the test by automatically annotating computer-mediated discourse using state-of-the-art language models.

CMD-AInotator supports **Computer-Mediated Discourse Analysis (CMDA)** by producing three *separate* annotation layers for each utterance in context:

* **Communicative acts and meta-acts** using the CMC Act Taxonomy (Herring, Das, & Penumarthy 2005; revised 2024 by Herring & Ge-Stadnyk)
* **Politeness / impoliteness** using the CMDA-oriented coding scheme in Herring (1994, 2004), grounded in Brown & Levinson (1987), with impoliteness subtypes from Culpeper (2011)
* **Meta-act flags** (e.g., non-bona fide; reported) as defined within the CMC Act framework (Herring, Das, & Penumarthy 2005)

Annotations are generated through structured prompting with **mandatory reasoning** and saved in a reproducible, debuggable format. The tool supports:

* **Multiple model backends**: OpenAI GPT, Anthropic Claude, Google Gemini, and Meta Llama
* **Corpus-agnostic processing**: works with any CMC dataset structure
* **Resumable runs** with comprehensive progress logging
* **Always-on reasoning**: every annotation includes step-by-step analysis
* **Robust error handling** with automatic retry and reasoning validation
* **Reproducibility** through fixed seeds and complete audit trails
* **No file modification**: original data files are never altered

## 💡 Why It Matters

Manual annotation of online discourse is slow, inconsistent, and hard to scale. Traditional rule-based systems struggle with context, sarcasm, and pragmatic nuance.

CMD-AInotator offers a **practical, theory-aware solution** that:

* Captures communicative intent beyond surface form
* Handles non-literal language (sarcasm, irony, rhetorical questions)
* Maintains theoretical grounding in established CMDA frameworks
* Scales to large datasets while preserving annotation quality
* Provides transparent reasoning for every decision

Perfect for CMC researchers studying **stance, identity, politeness, conflict, and solidarity** at scale.

> LLMs may be changing the game, but we still define the rules.

## 🧭 Annotation Schema

CMD-AInotator implements a **CMDA**-aligned annotation workflow. It applies the **CMC Act Taxonomy** for communicative acts (including meta-acts), and applies a **separate** politeness/impoliteness coding scheme.

### 🎙️ Communicative Act Labels (18 total)

| Label                 | Definition                                              | Example                                                      |
| --------------------- | ------------------------------------------------------- | ------------------------------------------------------------ |
| **Accept**            | Concur, agree, acquiesce, approve; acknowledge          | "Exactly this."; "I agree"                                   |
| **Apologize**         | Humble oneself, self-deprecate                          | "Sorry this happened to your family."                        |
| **Behave**            | Perform a virtual action                                | "*dances with joy"; "*sips tea"                              |
| **Claim**             | Make subjective assertion; unverifiable in principle    | "I do not understand the mentality of people who..."         |
| **Congratulate**      | Celebrate/praise accomplishment; encourage; validate    | "Well done!"; "You've got this!"                             |
| **Desire (Irrealis)** | Want, hope, wish; promise, predict; hypothetical        | "I wish they'd just play the game together."                 |
| **Direct**            | Command, demand; prohibit; permit; advise               | "You should try something else."                             |
| **Elaborate**         | Explain or paraphrase previous utterance                | "This isn't the first time it happened..."                   |
| **Greet**             | Greeting, leave-taking; formulaic well-being inquiries  | "Hello"; "How are you?"                                      |
| **Inform**            | Provide "factual" information (verifiable in principle) | "I recently played Terraria with friends..."                 |
| **Inquire**           | Seek information; make neutral proposals                | "What's up with people being upset about this?"              |
| **Invite**            | Seek participation; suggest; offer                      | "You might want to post this in another subreddit."          |
| **Manage**            | Organize, prompt, focus, open/close discussions         | "I have two thoughts about that..."                          |
| **React**             | Show listenership, engagement                           | "Lmao this is so dramatic."; "wow"                           |
| **Reject**            | Disagree, dispute, challenge                            | "Dude! You came here for answers and you are NOT listening." |
| **Repair**            | Clarify or seek clarification; correct misunderstanding | "Did you mean 'school holiday'?"                             |
| **Request**           | Seek action politely                                    | "Can someone explain this to me?"                            |
| **Thank**             | Express gratitude, appreciation                         | "Thanks for saying this."                                    |

### 🪞 Politeness & Impoliteness

Politeness and impoliteness are coded following **Herring (1994, 2004)** as part of the CMDA paradigm. This scheme is grounded in **Brown & Levinson (1987)**, and we additionally record impoliteness subtypes following **Culpeper (2011)**.

| Code   | Meaning                                                | Examples                                   |
| ------ | ------------------------------------------------------ | ------------------------------------------ |
| **+P** | Affirm positive face (desire to be liked, appreciated) | compliments, support, friendly humor       |
| **+N** | Respect negative face (desire for autonomy)            | hedging, deference, giving options         |
| **-P** | Attack positive face                                   | insults, mocking, condescension            |
| **-N** | Attack negative face                                   | commands, intrusive questions, impositions |

**Impoliteness subtypes** (Culpeper 2011): `[Insult]`, `[Condescension]`, `[Dismissal]`, `[Silencer]`, `[Threat]`, `[Negative association]`

### 🏷️ Meta-Acts

Meta-acts are treated as part of communicative-act analysis in the CMC Act framework (Herring, Das, & Penumarthy 2005).

| Tag               | Description                                     |
| ----------------- | ----------------------------------------------- |
| **non-bona fide** | Sarcasm, irony, jokes, rhetorical questions     |
| **reported**      | Quoting or paraphrasing others' speech/thoughts |

### CMDA reference

Herring, S. C. (2004). *Computer-mediated discourse analysis: An approach to researching online behavior.* In S. A. Barab, R. Kling, & J. H. Gray (Eds.), *Designing for Virtual Communities in the Service of Learning* (pp. 338–376). Cambridge University Press.

> Note: For comparability with published results, we treat the system prompt as versioned and **frozen** within a release.

## 🚀 Usage

```bash
# Annotate with default settings (GPT-4o with reasoning)
python run.py --xlsx your_data.xlsx

# Use different models
python run.py --xlsx your_data.xlsx --model claude-sonnet-4-20250514
python run.py --xlsx your_data.xlsx --model gemini-2.5-pro-preview-06-05

# Resume from previous run
python run.py --xlsx your_data.xlsx --resume previous_output.csv

# Debug mode (first 10 rows only)
python run.py --xlsx your_data.xlsx --debug
```

### Supported Models

* **OpenAI**: `gpt-4o-2024-08-06`, `o3-2025-04-16`
* **Anthropic**: `claude-sonnet-4-20250514`
* **Google**: `gemini-2.5-pro-preview-06-05`
* **Llama**: `meta-llama/Llama-3.1-8B-Instruct`

### Input Data Requirements

Your Excel file should contain at minimum:

* `Msg#`: message thread identifier
* `User ID`: speaker identifier
* `Message`: the utterance text

Optional columns (automatically handled):

* `Utterance #`: position in thread
* `Gender`, `Time`: user metadata
* `Reply to_ID`: for threaded conversations
* `Category`: for categorized data (e.g., "Original post", "Comment")

## 📂 Output Structure

Results are saved as a **single comprehensive CSV file** containing:

### Original Data

* All columns from your input Excel file (preserved exactly)

### Annotations

* `annotation_act`: primary communicative act (required)
* `annotation_politeness`: politeness code with optional subtype (e.g., `-P [Insult]`)
* `annotation_meta`: meta-act tags (comma-separated if multiple)
* `annotation_reasoning`: step-by-step reasoning (always included)

### Raw API Data

* `raw_prompt`: complete prompt sent to model
* `raw_response`: full model response
* `annotation_seed`: seed used for this annotation
* `annotation_timestamp`: when annotation was created

### Example Output Structure

```
your_data_annotated_gpt_4o_2024_08_06.csv
├── Msg# | User ID | Message | annotation_act | annotation_reasoning | ...
├── 1    | User1   | "Hello" | Greet         | "This is a greeting..." | ...
└── 2    | User2   | "Hi!"    | Greet         | "Response greeting..."  | ...
```

## 🔧 Key Features

### Mandatory Reasoning

* **Every annotation includes reasoning**: no exceptions, minimum 20 characters
* **Step-by-step analysis** following the CMDA annotation procedure
* **Transparent decision-making** for research validation and debugging

### Robust Processing

* **Automatic retry logic** with exponential backoff and multiple seeds
* **Enhanced validation** for reasoning quality and annotation format
* **Content policy handling** for sensitive content (marked as `__FLAGGED__`)
* **Comprehensive error tracking** with detailed logging

### Corpus Flexibility

* **Dynamic context building** adapts to threaded vs. sequential conversations
* **Missing metadata handling** works with incomplete user information
* **Universal system prompt** works across different CMC datasets
* **Corpus-specific backgrounds** for Game and Prison styles

### Data Integrity

* **No file modification**: original Excel files are never changed
* **Comprehensive output**: single CSV with all data, annotations, and metadata
* **Resumable processing**: skip already-annotated rows on restart
* **Checkpoint saving** every 20 rows for long runs

### Quality Assurance

* **Fixed seed reproducibility** with complete audit trails
* **Progress tracking** with success/failure/flagged counts
* **Validation at multiple levels**: JSON format, act labels, politeness codes
* **Reasoning requirement** prevents superficial annotations

## 🛠️ Installation & Setup

```bash
# Clone repository
git clone https://github.com/Wang-Haining/ainotator.git
cd ainotator

# Install dependencies
pip install pandas openpyxl tqdm

# For OpenAI models
pip install openai
export OPENAI_API_KEY="your-api-key-here"

# For Anthropic Claude models
pip install anthropic
export ANTHROPIC_API_KEY="your-api-key-here"

# For Google Gemini models
pip install google-generativeai
export GEMINI_API_KEY="your-api-key-here"

# For local Llama models
pip install transformers vllm
# Ensure GPU resources are available
```

## 📜 Version History

<details>
<summary>Click to expand version history</summary>

* **v0.5.0** *(Current)*

  * **Updated script name**: changed from `annotate.py` to `run.py`
  * **Enhanced model support**: added o3-* models for OpenAI
  * **Improved meta-act handling**: removed brackets from meta-act tags in output
  * **Always-on reasoning**: every annotation includes step-by-step analysis
  * **Simplified interface**: removed complex flags, reasoning is always required
  * **Comprehensive output**: single CSV with all data, annotations, and metadata
  * **Multi-model support**: OpenAI, Anthropic, Google, and Llama (local)
  * **Data preservation**: original files never modified
  * **Enhanced validation**: stricter reasoning and format requirements

* **v0.4.0**

  * **Always-on reasoning**: every annotation includes step-by-step analysis
  * **Simplified interface**: removed complex flags, reasoning is always required
  * **Comprehensive output**: single CSV with all data, annotations, and metadata
  * **Multi-model support**: OpenAI, Anthropic, Google, and Llama (local)
  * **Data preservation**: original files never modified
  * **Enhanced validation**: stricter reasoning and format requirements

* **v0.3.0**

  * **Corpus-agnostic**: one system prompt for all datasets
  * **Improved politeness framework**: added theoretical foundation and coding references
  * **Enhanced context**: background summaries, thread starters, local conversational context

* **v0.2.0**

  * **Multiple model support**: OpenAI (GPT-4o, O3) and local Llama-3.1
  * **Improved validation**: better format checking and annotation reproducibility
  * **Quality assurance**: comprehensive logging and checkpoint system

* **v0.1.0**

  * Initial prototype with communicative act classification
  * Basic politeness/impoliteness tagging and meta-acts
  * CoT reasoning toggle and resumable run logic

</details>

## 📄 License

* **Code**: MIT
* **Prompt text (system prompt)**: CC BY 4.0 (attribution requested for reuse and derivatives)

## 🤝 Contributions

For questions, suggestions, or collaboration opportunities, please open an issue on GitHub or contact [Yueru Yan](mailto:yueryan@iu.edu) or [Haining Wang](mailto:hw56@iu.edu).
