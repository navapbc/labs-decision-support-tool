import unittest
from unittest.mock import Mock, patch, MagicMock
from typing import List

import pytest

from src.embeddings.openai import OpenAIEmbedding


class TestOpenAIEmbedding:
    """Tests for the OpenAIEmbedding class."""

    @patch('src.embeddings.openai.OpenAI')
    @patch('src.embeddings.openai.tiktoken')
    def test_init(self, mock_tiktoken, mock_openai_client):
        """Test initialization of OpenAIEmbedding with default parameters."""
        # Setup mocks
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding

        # Create model with default parameters
        model = OpenAIEmbedding()
        
        # Verify initialization
        mock_openai_client.assert_called_once_with(api_key=None, base_url=None)
        mock_tiktoken.get_encoding.assert_called_once_with("cl100k_base")
        assert model._model_name == "text-embedding-3-small"
        assert model._tokenizer == mock_encoding

    @patch('src.embeddings.openai.OpenAI')
    @patch('src.embeddings.openai.tiktoken')
    def test_init_with_parameters(self, mock_tiktoken, mock_openai_client):
        """Test initialization of OpenAIEmbedding with custom parameters."""
        # Setup mocks
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding

        # Create model with custom parameters
        model = OpenAIEmbedding(
            model_name="text-embedding-3-large",
            api_key="test-api-key",
            base_url="https://custom.openai.com"
        )
        
        # Verify initialization
        mock_openai_client.assert_called_once_with(
            api_key="test-api-key", 
            base_url="https://custom.openai.com"
        )
        assert model._model_name == "text-embedding-3-large"

    @patch('src.embeddings.openai.OpenAI')
    def test_max_seq_length(self, mock_openai_client):
        """Test max_seq_length property for different models."""
        # Test default model
        model = OpenAIEmbedding()
        assert model.max_seq_length == 8191
        
        # Test other known models
        model = OpenAIEmbedding(model_name="text-embedding-3-large")
        assert model.max_seq_length == 8191
        
        model = OpenAIEmbedding(model_name="text-embedding-ada-002")
        assert model.max_seq_length == 8191
        
        # Test unknown model (should return default value)
        model = OpenAIEmbedding(model_name="unknown-model")
        assert model.max_seq_length == 8191

    @patch('src.embeddings.openai.OpenAI')
    @patch('src.embeddings.openai.tiktoken')
    def test_tokenizer(self, mock_tiktoken, mock_openai_client):
        """Test tokenizer property."""
        # Setup mocks
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding

        # Create model
        model = OpenAIEmbedding()
        
        # Verify tokenizer
        assert model.tokenizer == mock_encoding
        
    @patch('src.embeddings.openai.OpenAI')
    def test_encode_single_text(self, mock_openai_client):
        """Test encoding a single text string."""
        # Setup mocks
        mock_client = Mock()
        mock_openai_client.return_value = mock_client
        
        mock_embedding_data = Mock()
        mock_embedding_data.embedding = [0.1, 0.2, 0.3]
        
        mock_response = Mock()
        mock_response.data = [mock_embedding_data]
        
        mock_client.embeddings.create.return_value = mock_response
        
        # Create model and encode text
        model = OpenAIEmbedding()
        embedding = model.encode("This is a test.")
        
        # Verify API call
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["This is a test."]
        )
        
        # Verify embedding
        assert embedding == [0.1, 0.2, 0.3]
        
    @patch('src.embeddings.openai.OpenAI')
    def test_encode_multiple_texts(self, mock_openai_client):
        """Test encoding multiple text strings."""
        # Setup mocks
        mock_client = Mock()
        mock_openai_client.return_value = mock_client
        
        mock_embedding_data1 = Mock()
        mock_embedding_data1.embedding = [0.1, 0.2, 0.3]
        
        mock_embedding_data2 = Mock()
        mock_embedding_data2.embedding = [0.4, 0.5, 0.6]
        
        mock_response = Mock()
        mock_response.data = [mock_embedding_data1, mock_embedding_data2]
        
        mock_client.embeddings.create.return_value = mock_response
        
        # Create model and encode texts
        model = OpenAIEmbedding()
        texts = ["First text", "Second text"]
        embeddings = model.encode(texts)
        
        # Verify API call
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=texts
        )
        
        # Verify embeddings
        assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        
    @patch('src.embeddings.openai.OpenAI')
    def test_encode_ignores_progress_bar(self, mock_openai_client):
        """Test that show_progress_bar parameter doesn't affect API call."""
        # Setup mocks
        mock_client = Mock()
        mock_openai_client.return_value = mock_client
        
        mock_embedding_data = Mock()
        mock_embedding_data.embedding = [0.1, 0.2, 0.3]
        
        mock_response = Mock()
        mock_response.data = [mock_embedding_data]
        
        mock_client.embeddings.create.return_value = mock_response
        
        # Create model and encode text with progress bar
        model = OpenAIEmbedding()
        embedding = model.encode("This is a test.", show_progress_bar=True)
        
        # Verify API call (should be the same as without progress bar)
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["This is a test."]
        )
        
        # Verify embedding
        assert embedding == [0.1, 0.2, 0.3]