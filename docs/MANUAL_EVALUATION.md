# Manual evaluation

A small sanity check, not a benchmark: 12 questions, 5 papers, one run, judged by hand.

**Setup:**
- **Papers:** Attention Is All You Need, BERT, RAG, ResNet and LoRA (406 passages).
- **Models:** bge-small-en-v1.5 for embeddings, qwen2.5:7b at temperature 0 for answers.
- **Settings:** the defaults (top_k 5, threshold 0.70).

I wrote the questions down before running them, ran each once, and didn't tune anything afterwards.
I swapped the Adam paper for LoRA before running anything, because arXiv kept timing out on Adam's ID.

## Results

| # | Type | Question | Top score | Top paper | Result | Notes |
|---|---|---|---|---|---|---|
| A1 | answerable | By how much does LoRA reduce the number of trainable parameters compared with fine-tuning GPT-3 175B? | 0.779 | LoRA | answered | correct ("10,000 times"), supported |
| A2 | answerable | What is the difference between RAG-Sequence and RAG-Token? | 0.758 | RAG | answered | correct, supported |
| A3 | answerable | How many layers, hidden units and attention heads does BERT-base have? | 0.772 | BERT | answered | correct (12/768/12), supported |
| A4 | answerable | What problem do deep residual networks address in very deep plain networks? | 0.797 | ResNet | answered | mostly right; says "deeper than 34 layers", which misreads the cited passage, and never names the degradation problem |
| P1 | paraphrased | Why do shortcut connections make very deep networks easier to train? | 0.771 | ResNet | answered | supported |
| P2 | paraphrased | How does the Transformer avoid overfitting during training? | 0.718 | LoRA | **abstained** | **false abstention:** retrieval returned LoRA passages, and the Transformer's dropout passages weren't in the top 20 |
| P3 | paraphrased | How does BERT learn from the words on both sides of a token at the same time? | 0.765 | BERT | answered | partly supported; "by using the self-attention mechanism" isn't in the cited passage, and masked LM isn't mentioned |
| S1 | paper selection | Which model combines a retriever over Wikipedia with a sequence-to-sequence generator? | 0.783 | RAG | answered | supported |
| S2 | paper selection | What top-5 error did the ensemble of residual networks achieve on the ImageNet test set? | 0.845 | ResNet | answered | correct (3.57%), supported |
| U1 | unrelated | What is the capital of Australia? | 0.477 | RAG | abstained | correct |
| U2 | unrelated | How do I fix a flat bicycle tire? | 0.470 | LoRA | abstained | correct |
| U3 | unrelated | How does AlphaFold predict protein structures? | 0.659 | Transformer | abstained | correct |

## Takeaways

- **Retrieval:** the right paper came first for 8 of the 9 answerable questions.
- **Answer quality:** 8 of 9 were answered. 6 were fully supported by their citations, A4 mostly,
  and P3 partly.
- **The one miss (P2)** was a retrieval problem, not the threshold. It scored 0.718, passed the
  threshold, and the model then said the evidence was insufficient.
- **The threshold** separated everything here, but only just: the AlphaFold question scored 0.659,
  and the weakest answerable one scored 0.718.
- **The main weakness:** answers can add details the cited passage doesn't contain. The app checks
  that citations exist, not that they support the sentence.
- **Average latency:** about 10 seconds per answer. Abstentions return immediately because the LLM
  isn't called.

## Limits

- **Sample:** 12 questions on well-known ML papers, written and judged by me.
- **Coverage:** one run, default settings only, and no comparison of thresholds or models.
