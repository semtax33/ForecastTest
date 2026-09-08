# Text IE GPU Runtime

The learned semantic challenger is fail-closed and requires CUDA. It never
silently falls back to CPU. The deterministic spaCy/DSL parser remains usable
without these optional packages.

Install the verified Windows environment into the Arcana virtual environment:

```powershell
& 'D:\Programming\python_example\Arcana\.venv-llama\Scripts\python.exe' `
  -m pip install -r requirements\semantic-gpu-cu126.txt
```

Verify the CUDA runtime and all three base encoders:

```powershell
& 'D:\Programming\python_example\Arcana\.venv-llama\Scripts\python.exe' `
  -m scripts.architecture.encoder_gpu_compatibility
```

The compatibility result is not a performance benchmark. Base encoders have no
task-specific concept, binding, or role heads, and cannot become a runtime
champion until independently adjudicated source-slice benchmarks exist.

`nlpaueb/sec-bert-shape` receives its required numeric-shape preprocessing.
spaCy supplies token boundaries; known model-vocabulary shapes are preserved and
unknown numeric shapes become `[NUM]`.

Download the pinned learned-span challengers into the project Bronze model
store without placing large weights under source control:

```powershell
& 'D:\Programming\python_example\Arcana\.venv-llama\Scripts\python.exe' `
  -m scripts.architecture.download_text_ie_span_models_v1
```

The generated manifest records immutable Hugging Face revisions and SHA-256
digests. BERT-SL1000/Cal-BERT-SL1000 are SEC span candidates; GLiNER2 is an IR
span candidate. None receives Fact or valuation authority from installation.
