# Embedding Models

This module provides an abstraction for embedding models used in the application.

## Overview

The application uses embeddings to:
1. Convert text chunks into vector representations during ingestion
2. Convert query text into vectors for similarity search during retrieval

This module provides a common interface (`EmbeddingModel`) that can be implemented by different embedding model providers.

## Available Models

- `MPNetEmbedding`: Uses the SentenceTransformer library with MPNet models (default)
- `MockEmbeddingModel`: For testing purposes, generates deterministic embeddings based on text length

## Usage

Use the app_config to get the embedding model:

```python
from src.app_config import app_config

# Get the configured embedding model
embedding_model = app_config.sentence_transformer

# Generate an embedding for a single text
query_embedding = embedding_model.encode("What is WIC?")

# Generate embeddings for multiple texts
texts = ["First document", "Second document", "Third document"]
embeddings = embedding_model.encode(texts)
```

## Adding New Embedding Models

To add a new embedding model:

1. Create a new class that implements the `EmbeddingModel` interface
2. Implement all required methods and properties:
   - `max_seq_length` property
   - `tokenizer` property
   - `encode()` method

Example:

```python
from src.embeddings.model import EmbeddingModel

class MyCustomEmbedding(EmbeddingModel):
    def __init__(self, model_name: str):
        # Initialize your model
        pass
    
    @property
    def max_seq_length(self) -> int:
        return 512  # Maximum sequence length supported
    
    @property
    def tokenizer(self):
        # Return your tokenizer
        pass
    
    def encode(self, texts, show_progress_bar=False):
        # Implement encoding logic
        pass
```

3. Update the `app_config.py` file to use your new model as needed