---
status: accepted
---

# Select financial encoders by source slice

Yiyang FinBERT, FLANG-SpanBERT, and SEC-BERT-SHAPE remain benchmark candidates rather than runtime champions. Each candidate must be fine-tuned and evaluated on independently adjudicated `10-K`, `10-Q`, IR prepared-remarks, and IR Q&A slices for concept, binding, and role tasks. Base encoders never act as task heads, and prior beliefs about domain fit cannot authorize source-based routing. Runtime inference loads one task head at a time on CUDA and evicts it before loading the next head so the 4 GB deployment GPU is not required to hold all heads simultaneously.
