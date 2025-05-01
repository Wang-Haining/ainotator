# 🤖 AInotator: Annotate Utterance with AI

LLMs are rapidly catching up — but can they understand what is meant, not just what is said?
**AInotator** puts this question to the test. 
It is a lightweight but powerful framework for **automated utterance-level annotation** in **computer-mediated communication (CMC)**, powered by OpenAI models.

Given an Excel sheet of utterances with conversational context, the system applies a linguistically grounded schema to assign:

- **Communicative Act Labels** (e.g., Accept, Request, Reject)
- **Politeness Tags** following Herring (1994) and Culpeper (2011a)
- **Meta-Acts** (e.g., [non-bona fide], [reported])

Annotations are generated through structured prompting and saved in a reproducible, debuggable format. The tool supports:

- Resumable runs with progress logging
- Chain-of-thought (CoT) reasoning mode
- Reproducibility through fixed seeds and audit logs

## 🧭 Annotation Schema

The model follows a taxonomy adapted from CMC pragmatics and politeness theory. Below is a summary of the categories used during annotation:

### 🎙️ Communicative Act Labels

| Label          | Example                                                              |
|----------------|----------------------------------------------------------------------|
| Accept         | “Exactly this.”                                                      |
| Apologize      | “Sorry this happened to your family.”                                |
| Claim          | “I do not understand the mentality of people who...”                 |
| Desire         | “I wish they’d just play the game together.”                         |
| Direct         | “You should try something else.”                                     |
| Elaborate      | “This isn’t the first time it happened...”                           |
| Inform         | “I recently played Terraria with friends...”                         |
| Inquire        | “What’s up with people being upset about this?”                      |
| Invite         | “You might want to post this in another subreddit.”                  |
| React          | “Lmao this is so dramatic.”                                          |
| Reject         | “Dude! You came here for answers and you are NOT listening.”         |
| Request        | “Can someone explain this to me?”                                    |
| Thank          | “Thanks for saying this.”                                            |

*(Less common labels like Behave, Greet, Manage, Repair are included but rarely observed.)*

### 🪞 Politeness & Impoliteness (Herring, 1994; Culpeper, 2011a)

| Code      | Meaning                                     | Examples                                        |
|-----------|---------------------------------------------|-------------------------------------------------|
| +P        | Positive politeness                         | Compliments, friendly joking                   |
| +N        | Negative politeness                         | Hedging, deference, giving options             |
| –P        | Violation of positive politeness            | Sarcasm, insults, mocking                      |
| –N        | Violation of negative politeness            | Commands, strong obligations, intrusive Qs     |

Impoliteness subtypes (e.g., `–P [Insult]`, `–P [Dismissal]`) are derived from Culpeper's framework.

### 🏷️ Meta-Acts

| Tag            | Description                                         |
|----------------|-----------------------------------------------------|
| [non-bona fide] | Sarcasm, jokes, rhetorical questions                |
| [reported]      | Quoting or paraphrasing others’ speech or thoughts  |

---

## 🚀 Usage

```bash
python run.py 
python run.py --cot  # for reasoning
```

## 📂 Output

Results are saved under `annotations/seed_<SEED>[_cot]/`:

- `annot_raw.parquet`: full prompt/response logs
- `annot_clean.csv`: parsed annotations only
- `annot_seq.csv`: aligned with the original Excel input

## 💡 Why It Matters

Manual annotation of online discourse is slow, inconsistent, and hard to scale.

AInotator offers a practical, theory-aware solution — making it ideal for CMC researchers studying stance, identity, politeness, conflict, and solidarity at scale.

> LLMs may be changing the game — but we still define the rules.
 
## 🛠️ Contributions
Contributions are welcome! Feel free to open an issue or submit a pull request.

## 📜 Version History

- **v0.0.2**  
  Enhanced prompt context with:
  - Background summary of the original Reddit post  
  - Inclusion of all thread-starting messages (Msg# == 1)  
  - Local conversational context (previous, target, next messages)  
  - Speaker metadata (User ID, gender, time, utterance ID)  
  Improved format validation and annotation reproducibility.

- **v0.0.1**  
  Initial prototype with support for communicative act classification, politeness/impoliteness tags, and meta-acts. Included CoT reasoning toggle and resumable run logic.


---