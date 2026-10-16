# Manual evaluation

> **This is a small manual sanity evaluation, not a statistically robust benchmark.**
> 12 questions, 5 papers, one run, judged by one reviewer. Its purpose is only to check whether
> the current design, in particular the `0.70` evidence threshold, behaves reasonably.
> Nothing was tuned on these results.

## Setup

| | |
|---|---|
| Date | 2026-10-16 |
| Corpus | 5 arXiv papers, 406 passages, all indexed: Attention Is All You Need (`1706.03762`), BERT (`1810.04805`), Retrieval-Augmented Generation (`2005.11401`), Deep Residual Learning (`1512.03385`), LoRA (`2106.09685`) |
| Embeddings | `BAAI/bge-small-en-v1.5` (384 dimensions) |
| Language model | `qwen2.5:7b` through Ollama, temperature 0 |
| Settings | defaults: `top_k = 5`, `RAG_MIN_SCORE = 0.70`, chunks of 150 words with 30 overlap |
| Method | each question was written down **before** running and sent once to `POST /ask` (all papers searched) and `POST /search` (top 3). No question was changed, dropped or re-run. |

One paper was swapped before any question was run: the Adam paper (`1412.6980`) could not be
imported because arXiv stalled for 43 s and then answered HTTP 429 for that one ID, so LoRA took its place.

## How results were judged

- **Top score**: the highest cosine similarity returned by `/search`.
- **Retrieval relevant**: the top result comes from the paper that answers the question, and a passage
  containing the answer appears in the top 3.
- **Supported by citation**: every claim in the answer was checked against the **full text** of the
  passage it cites. "Partly" means some claims are not backed by the cited passage.

The judging is subjective and was done by reading the passages, by the person who built the system,
using prior knowledge of these well-known papers. It has not been independently reviewed.

## Results

| # | Kind | Question | Top score | Top paper | Retrieval relevant | Result | Supported by citation |
|---|---|---|---|---|---|---|---|
| A1 | answerable | By how much does LoRA reduce the number of trainable parameters compared with fine-tuning GPT-3 175B? | 0.779 | LoRA | yes (answer passage ranked 2nd) | answered | **yes**: "10,000 times" is in the cited passage |
| A2 | answerable | What is the difference between RAG-Sequence and RAG-Token? | 0.758 | RAG | yes | answered | **yes** |
| A3 | answerable | How many layers, hidden units and attention heads does BERT-base have? | 0.772 | BERT | yes (answer passage ranked 2nd) | answered | **yes**: cited passage contains L=12, H=768, A=12 |
| A4 | answerable | What problem do deep residual networks address in very deep plain networks? | 0.797 | ResNet | yes | answered | **mostly**: the core claim is supported, but "plain networks *deeper than 34 layers*" misstates the cited passage (34-layer vs 18-layer), and the "degradation problem" is never named |
| P1 | paraphrased | Why do shortcut connections make very deep networks easier to train? | 0.771 | ResNet | yes | answered | **yes** |
| P2 | paraphrased | How does the Transformer avoid overfitting during training? | 0.718 | **LoRA** | **no** | **abstained** (`model_insufficient_evidence`) | n/a: **false abstention** |
| P3 | paraphrased | How does BERT learn from the words on both sides of a token at the same time? | 0.765 | BERT | partly (right paper; the masked-LM passage was not in the top 3) | answered | **partly**: "jointly conditions on both left and right context" is supported by the abstract, but "by using the self-attention mechanism" is not in the passage it cites and misses the key mechanism (masked language modelling) |
| S1 | paper selection | Which model combines a retriever over Wikipedia with a sequence-to-sequence generator? | 0.783 | RAG | yes | answered | **yes** |
| S2 | paper selection | What top-5 error did the ensemble of residual networks achieve on the ImageNet test set? | 0.845 | ResNet | yes | answered | **yes**: 3.57% appears in both cited passages |
| U1 | unrelated | What is the capital of Australia? | 0.477 | RAG (irrelevant) | n/a | **abstained** (`no_relevant_passages`) | correct abstention |
| U2 | unrelated | How do I fix a flat bicycle tire? | 0.470 | LoRA (irrelevant) | n/a | **abstained** (`no_relevant_passages`) | correct abstention |
| U3 | unrelated | How does AlphaFold predict protein structures? | **0.659** | Transformer (irrelevant) | n/a | **abstained** (`no_relevant_passages`) | correct abstention |

## Summary

| | Result |
|---|---|
| Right paper at rank 1, for the 9 in-corpus questions | 8 of 9 (miss: P2) |
| Passage with the answer in the top 3, for the 9 in-corpus questions | 7 of 9 clearly, 1 partly (P3), 1 miss (P2) |
| In-corpus questions answered | 8 of 9 |
| Answers fully supported by their citations | 6 of 8 (A1, A2, A3, P1, S1, S2); 1 mostly (A4); 1 partly (P3) |
| False abstentions | 1 of 9 (P2) |
| Unrelated questions correctly abstained | 3 of 3 |
| Answer latency | about 9–12 s per generated answer (one 19 s first call); abstentions are instant because the model is not called |

## What the threshold did

Highest retrieval score per question, sorted:

```text
in-corpus questions   0.718  0.758  0.771  0.772  0.779  0.783  0.797  0.845   (P2 = 0.718, wrong paper)
unrelated questions   0.470  0.477  0.659
                                  threshold 0.70
```

- The 0.70 threshold separated the unrelated questions from the in-corpus ones in all 12 cases,
  and it never caused a false abstention. The one false abstention (P2) scored 0.718, so it passed the
  threshold, and was then refused by the language model.
- **The margin is thin.** The closest unrelated question (AlphaFold, a plausible neighbour of this corpus)
  scored 0.659, only 0.06 below the weakest in-corpus top score. A different corpus or a more closely
  related off-topic question could land on the wrong side. The threshold is a heuristic, not a guarantee.

## Observations

1. **P2 is a retrieval miss, not a threshold problem.** The Transformer's "Residual Dropout" and "label
   smoothing" passages exist in the database, but none ranked in the top 20 of 406 passages for this
   paraphrase; the top results were LoRA passages about memory use and hardware cost. Whether restricting
   the question to the Transformer paper would have helped was not tried, since it would no longer be
   the same question.
2. **Generated answers can overreach their citations (A4, P3).** The system verifies that every `[n]`
   points to a real passage, but it does not verify that the sentence is entailed by that passage. A small
   local model sometimes adds a plausible detail. This is the main quality limit of the simple RAG design.
3. **Retrieval ranked the best passage 2nd rather than 1st in two cases (A1, A3)**, which is why the
   prompt uses several passages rather than one.
4. **Unrelated questions always return nearest neighbours** (for example, "capital of Australia" retrieved a
   RAG example about the middle ear). Without the threshold, the language model would be asked to answer
   from irrelevant text.

## Limits of this evaluation

- 12 questions and 5 papers, all well-known machine-learning papers; no statistical claims can be made.
- Questions were written by the system's builder, not by independent users.
- The judging is one person's reading of the passages, not blind or repeated.
- One run at temperature 0; a re-run on a different machine could differ slightly.
- Only the default settings were tested. No alternative thresholds, chunk sizes or models were compared.

## Reproducing

Import and index the five papers (Papers page), then ask the questions above on the Ask page, or send
them to `POST /ask`. `python3 scripts/smoke_test.py` automates a smaller check (one answerable and one
unrelated question, with citation verification).
