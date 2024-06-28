import math


class MockSentenceTransformer:
    def __init__(self, *args, **kwargs):
        # Imitate multi-qa-mpnet-base-dot-v1
        self.max_seq_length = 512
        self.tokenizer = MockTokenizer()

    def encode(self, text, **kwargs):
        """
        Encode text into a 768-dimensional embedding that allows for similarity comparison via the dot product.
        The direction of the vector maps to the average word length of the text.
        """

        tokens = self.tokenizer.tokenize(text)
        average_token_length = sum(len(token) for token in tokens) / len(tokens)

        # Map average length to between 0 and 90 degrees
        # Then project that angle on the first two dimensions and pad the rest as 0
        return [
            math.cos(math.pi / 2 * average_token_length),
            math.sin(math.pi / 2 * average_token_length),
        ] + [0] * 766


class MockTokenizer:
    def tokenize(self, text):
        return text.split()
