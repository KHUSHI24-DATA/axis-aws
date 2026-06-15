import boto3
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_aws import BedrockEmbeddings
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings

from app.core.config import settings
# If you plan on adding other embeddings, import them here
# from some_other_module import AnotherEmbeddingClass


class EmbeddingsFactory:
    @staticmethod
    def create():
        """
        Factory method to create an embeddings instance based on .env config.
        """
        # Suppose your .env has a value like EMBEDDINGS_PROVIDER=openai
        embeddings_provider = settings.EMBEDDINGS_PROVIDER.lower()

        if embeddings_provider == "openai":
            return OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                openai_api_base=settings.OPENAI_API_BASE,
                model=settings.OPENAI_EMBEDDINGS_MODEL
            )
        elif embeddings_provider == "azure_openai":
            return AzureOpenAIEmbeddings(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                openai_api_version=settings.AZURE_OPENAI_API_VERSION,
                api_key=settings.AZURE_OPENAI_API_KEY,
                azure_deployment=(
                    settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT
                    or settings.AZURE_OPENAI_DEPLOYMENT
                ),
            )
        elif embeddings_provider == "dashscope":
            return DashScopeEmbeddings(
                model=settings.DASH_SCOPE_EMBEDDINGS_MODEL,
                dashscope_api_key=settings.DASH_SCOPE_API_KEY
            )
        elif embeddings_provider == "ollama":
            return OllamaEmbeddings(
                model=settings.OLLAMA_EMBEDDINGS_MODEL,
                base_url=settings.OLLAMA_API_BASE
            )
        elif embeddings_provider == "bedrock":
            if not settings.AWS_BEDROCK_REGION:
                raise ValueError("AWS_BEDROCK_REGION is required for Bedrock embeddings")
            if not settings.AWS_BEDROCK_EMBEDDINGS_MODEL:
                raise ValueError(
                    "AWS_BEDROCK_EMBEDDINGS_MODEL is required for Bedrock embeddings"
                )

            session_kwargs = {}
            if settings.AWS_BEDROCK_PROFILE:
                session_kwargs["profile_name"] = settings.AWS_BEDROCK_PROFILE
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                session_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                session_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
                if settings.AWS_SESSION_TOKEN:
                    session_kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

            boto3_session = boto3.Session(**session_kwargs)
            client = boto3_session.client(
                "bedrock-runtime",
                region_name=settings.AWS_BEDROCK_REGION,
            )

            return BedrockEmbeddings(
                client=client,
                model_id=settings.AWS_BEDROCK_EMBEDDINGS_MODEL,
            )

        # Extend with other providers:
        # elif embeddings_provider == "another_provider":
        #     return AnotherEmbeddingClass(...)
        else:
            raise ValueError(f"Unsupported embeddings provider: {embeddings_provider}")
