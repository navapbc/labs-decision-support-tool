import math


class MockSentenceTransformer:
    def __init__(self, *args, **kwargs):
        # Imitate multi-qa-mpnet-base-dot-v1
        self.max_seq_length = 512
        self.tokenizer = MockTokenizer()

    def encode(self, text, **kwargs):
        """
        Encode text into a 768-dimensional embedding that allows for similarity comparison via the dot product.
        The embedding represents the average word length of the text
        """

        tokens = self.tokenizer.tokenize(text)
        average_token_length = sum(len(token) for token in tokens) / len(tokens)

        # Convert average word length to an angle, and pad the vector to length 768
        angle = (1 / average_token_length) * 2 * math.pi
        embedding = [math.cos(angle), math.sin(angle)] + ([0] * 766)

        # Normalize the embedding before returning it
        return [x / sum(embedding) for x in embedding]


class MockTokenizer:
    def tokenize(self, text):
        return text.split()
