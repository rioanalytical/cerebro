# cerebro
agentic flow to mimic PM

[
https://openaipublic.blob.core.windows.net/gpt-2-exports/vocab.bpe
](https://openaipublic.blob.core.windows.net/gpt-2-exports/encoder.json

https://openaipublic.blob.core.windows.net/gpt-2-exports/vocab.bpe

Copy them into your offline environment (say under ./gpt2_tokenizer/).)

import tiktoken

# Point to local GPT-2 tokenizer files
enc = tiktoken.Encoding(
    name="gpt2-offline",
    pat_str=r"""'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+""",
    mergeable_ranks=tiktoken.load_tiktoken_bpe("./gpt2_tokenizer/vocab.bpe"),
    special_tokens={}
)

# Encode & decode
tokens = enc.encode("king rules the land")
print("Token IDs:", tokens)
print("Back to text:", enc.decode(tokens))
