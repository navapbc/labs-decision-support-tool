import math


class MockSentenceTransformer:
    def __init__(self, *args, **kwargs):
        # Imitate multi-qa-mpnet-base-dot-v1
        self.max_seq_length = 512
        self.tokenizer = MockTokenizer()

    def _encode_one(self, text):
        tokens = self.tokenizer.tokenize(text)
        average_token_length = sum(len(token) for token in tokens) / len(tokens)

        # Map average length to between 0 and 90 degrees
        # Then project that angle on the first two dimensions and pad the rest as 0
        return [
            math.cos(math.pi / 2 * average_token_length),
            math.sin(math.pi / 2 * average_token_length),
        ] + [0] * 766

    def encode(self, texts, **kwargs):
        """
        Encode text into a 768-dimensional embedding that allows for similarity comparison via the dot product.
        The direction of the vector maps to the average word length of the text.
        """

        if isinstance(texts, str):
            return self._encode_one(texts)
        return [self._encode_one(text) for text in texts]


class MockTokenizer:
    def tokenize(self, text, **kwargs):
        return text.split()
