# 🤖 CMD-AInotator: Annotate Computer-Mediated Discourse with LLMs

Can LLMs understand what is meant, not just what is said?
**AInotator** puts this question to the test by automatically annotating computer-mediated discourse using state-of-the-art language models.

For each utterance in context, we assign:

- **Communicative Act Labels** (e.g., Accept, Request, Reject)
- **Politeness Tags** following Brown & Levinson (1987), Herring (1994) and Culpeper (2011)
- **Meta-Acts** (e.g., non-bona fide, reported)

Annotations are generated through structured prompting with **mandatory reasoning** and saved in a reproducible, debuggable format. The tool supports:

- **Multiple model backends**: OpenAI GPT, Anthropic Claude, Google Gemini, and Meta Llama
- **Corpus-agnostic processing**: Works with any CMC dataset structure
- **Resumable runs** with comprehensive progress logging
- **Always-on reasoning**: Every annotation includes step-by-step analysis
- **Robust error handling** with automatic retry and reasoning validation
- **Reproducibility** through fixed seeds and complete audit trails
- **No file modification**: Original data files are never altered

## 💡 Why It Matters

Manual annotation of online discourse is slow, inconsistent, and hard to scale. Traditional rule-based systems struggle with context, sarcasm, and pragmatic nuance.

AInotator offers a **practical, theory-aware solution** that:
- Captures communicative intent beyond surface form
- Handles non-literal language (sarcasm, irony, rhetorical questions)
- Maintains theoretical grounding in established CMC frameworks
- Scales to large datasets while preserving annotation quality
- Provides transparent reasoning for every decision

Perfect for CMC researchers studying **stance, identity, politeness, conflict, and solidarity** at scale.

> LLMs may be changing the game — but we still define the rules.

## 🧭 Annotation Schema

The model follows the **CMC Act Taxonomy** (Herring, Das, and Penumarthy 2005; revised 2024) adapted from CMC pragmatics and politeness theory.

### 🎙️ Communicative Act Labels (18 total)

| Label          | Definition | Example                                                              |
|----------------|------------|----------------------------------------------------------------------|
| **Accept**     | Concur, agree, acquiesce, approve; acknowledge | "Exactly this."; "I agree" |
| **Apologize**  | Humble oneself, self-deprecate | "Sorry this happened to your family." |
| **Behave**     | Perform a virtual action | "*dances with joy"; "*sips tea" |
| **Claim**      | Make subjective assertion; unverifiable in principle | "I do not understand the mentality of people who..." |
| **Congratulate** | Celebrate/praise accomplishment; encourage; validate | "Well done!"; "You've got this!" |
| **Desire (Irrealis)** | Want, hope, wish; promise, predict; hypothetical | "I wish they'd just play the game together." |
| **Direct**     | Command, demand; prohibit; permit; advise | "You should try something else." |
| **Elaborate**  | Explain or paraphrase previous utterance | "This isn't the first time it happened..." |
| **Greet**      | Greeting, leave-taking; formulaic well-being inquiries | "Hello"; "How are you?" |
| **Inform**     | Provide "factual" information (verifiable in principle) | "I recently played Terraria with friends..." |
| **Inquire**    | Seek information; make neutral proposals | "What's up with people being upset about this?" |
| **Invite**     | Seek participation; suggest; offer | "You might want to post this in another subreddit." |
| **Manage**     | Organize, prompt, focus, open/close discussions | "I have two thoughts about that..." |
| **React**      | Show listenership, engagement | "Lmao this is so dramatic."; "wow" |
| **Reject**     | Disagree, dispute, challenge | "Dude! You came here for answers and you are NOT listening." |
| **Repair**     | Clarify or seek clarification; correct misunderstanding | "Did you mean 'school holiday'?" |
| **Request**    | Seek action politely | "Can someone explain this to me?" |
| **Thank**      | Express gratitude, appreciation | "Thanks for saying this." |

### 🪞 Politeness & Impoliteness

Based on **Brown & Levinson (1987)** Politeness Theory: Positive politeness aims to enhance the addressee's self-esteem, while negative politeness respects their autonomy.

| Code      | Meaning                                     | Examples                                        |
|-----------|---------------------------------------------|-------------------------------------------------|
| **+P**    | Affirm positive face (desire to be liked, appreciated) | Compliments, support, friendly humor |
| **+N**    | Respect negative face (desire for autonomy) | Hedging, deference, giving options |
| **-P**    | Attack positive face | Insults, mocking, condescension |
| **-N**    | Attack negative face | Commands, intrusive questions, impositions |

**Impoliteness subtypes** (Culpeper 2011): `[Insult]`, `[Condescension]`, `[Dismissal]`, `[Silencer]`, `[Threat]`, `[Negative association]`

### 🏷️ Meta-Acts

| Tag            | Description                                         |
|----------------|-----------------------------------------------------|
| **non-bona fide** | Sarcasm, irony, jokes, rhetorical questions     |
| **reported**      | Quoting or paraphrasing others' speech/thoughts |

---

## 🚀 Usage

```bash
# Annotate with default settings (GPT-4o with reasoning)
python run.py --xlsx your_data.xlsx

# use different models
python run.py --xlsx your_data.xlsx --model claude-sonnet-4-20250514
python run.py --xlsx your_data.xlsx --model gemini-2.5-pro-preview-06-05

# resume from previous run
python run.py --xlsx your_data.xlsx --resume previous_output.csv

# debug mode (first 10 rows only)
python run.py --xlsx your_data.xlsx --debug

```

### Supported Models
- **OpenAI**: `gpt-4o-2024-08-06`, `o3-2025-04-16`
- **Anthropic**: `claude-sonnet-4-20250514`
- **Google**: `gemini-2.5-pro-preview-06-05`
- **Llama**: `meta-llama/Llama-3.1-8B-Instruct`

### Input Data Requirements
Your Excel file should contain at minimum:
- `Msg#`: Message thread identifier
- `User ID`: Speaker identifier  
- `Message`: The utterance text

Optional columns (automatically handled):
- `Utterance #`: Position in thread
- `Gender`, `Time`: User metadata
- `Reply to_ID`: For threaded conversations
- `Category`: For categorized data (e.g., "Original post", "Comment")

## 📂 Output Structure

Results are saved as a **single comprehensive CSV file** containing:

### Original Data
- All columns from your input Excel file (preserved exactly)

### Annotations
- `annotation_act`: Primary communicative act (required)
- `annotation_politeness`: Politeness code with optional subtype (e.g., "-P [Insult]")
- `annotation_meta`: Meta-act tags (comma-separated if multiple)
- `annotation_reasoning`: Step-by-step reasoning (always included)

### Raw API Data
- `raw_prompt`: Complete prompt sent to model
- `raw_response`: Full model response
- `annotation_seed`: Seed used for this annotation
- `annotation_timestamp`: When annotation was created

### Example Output Structure
```
your_data_annotated_gpt_4o_2024_08_06.csv
├── Msg# | User ID | Message | annotation_act | annotation_reasoning | ...
├── 1    | User1   | "Hello" | Greet          | "This is a greeting..." | ...
└── 2    | User2   | "Hi!"   | Greet          | "Response greeting..."  | ...
```

## 🔧 Key Features

### Mandatory Reasoning
- **Every annotation includes reasoning**: No exceptions, minimum 20 characters
- **Step-by-step analysis** following CMC annotation procedure
- **Transparent decision-making** for research validation and debugging

### Robust Processing
- **Automatic retry logic** with exponential backoff and multiple seeds
- **Enhanced validation** for reasoning quality and annotation format
- **Content policy handling** for sensitive content (marked as `__FLAGGED__`)
- **Comprehensive error tracking** with detailed logging

### Corpus Flexibility
- **Dynamic context building** adapts to threaded vs. sequential conversations
- **Missing metadata handling** works with incomplete user information
- **Universal system prompt** works across different CMC datasets
- **Corpus-specific backgrounds** for Game and Prison styles

### Data Integrity
- **No file modification**: Original Excel files are never changed
- **Comprehensive output**: Single CSV with all data, annotations, and metadata
- **Resumable processing**: Skip already-annotated rows on restart
- **Checkpoint saving** every 20 rows for long runs

### Quality Assurance
- **Fixed seed reproducibility** with complete audit trails
- **Progress tracking** with success/failure/flagged counts
- **Validation at multiple levels**: JSON format, act labels, politeness codes
- **Reasoning requirement** prevents superficial annotations

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

- **v0.5.0** *(Current)*
  - **Updated script name**: Changed from `annotate.py` to `run.py`
  - **Enhanced model support**: Added o3-* models for OpenAI
  - **Improved meta-act handling**: Removed brackets from meta-act tags in output
  - **Always-on reasoning**: Every annotation includes step-by-step analysis
  - **Simplified interface**: Removed complex flags, reasoning is always required
  - **Comprehensive output**: Single CSV with all data, annotations, and metadata
  - **Multi-model support**: OpenAI, Anthropic, Google, and Llama (local)
  - **Data preservation**: Original files never modified
  - **Enhanced validation**: Stricter reasoning and format requirements

- **v0.4.0**  
  - **Always-on reasoning**: Every annotation includes step-by-step analysis
  - **Simplified interface**: Removed complex flags, reasoning is always required
  - **Comprehensive output**: Single CSV with all data, annotations, and metadata
  - **Multi-model support**: OpenAI, Anthropic, Google, and Llama (local)
  - **Data preservation**: Original files never modified
  - **Enhanced validation**: Stricter reasoning and format requirements

- **v0.3.0**  
  - **Corpus-agnostic**: One system prompt for all datasets
  - **Improved politeness framework**: Added Brown & Levinson theoretical foundation
  - **Enhanced context**: Background summaries, thread starters, local conversational context

- **v0.2.0**  
  - **Multiple model support**: OpenAI (GPT-4o, O3) and local Llama-3.1
  - **Improved validation**: Better format checking and annotation reproducibility
  - **Quality assurance**: Comprehensive logging and checkpoint system

- **v0.1.0**  
  - Initial prototype with communicative act classification
  - Basic politeness/impoliteness tagging and meta-acts
  - CoT reasoning toggle and resumable run logic

</details>

## 📄 License

MIT

## 🤝 Contributions

For questions, suggestions, or collaboration opportunities, please open an issue on GitHub or contact Haining Wang (hw56@iu.edu).
