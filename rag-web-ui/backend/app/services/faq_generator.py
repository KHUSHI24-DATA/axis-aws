"""FAQ Generation Service - Generates FAQs from document content using LLM"""

import logging
import json
import re
from typing import List, Dict, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from app.services.llm.llm_factory import LLMFactory
from app.core.config import settings
from app.utils.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


class FAQGeneratorService:
    """Service for generating FAQs from document content using LLM"""

    def __init__(self):
        self.llm = LLMFactory.create()
        self.max_faqs = 30
        self.min_faqs = 3
        self.timeout_seconds = 60

    async def determine_faq_count(
        self,
        content: str,
        max_faqs: int = 30,
        min_faqs: int = 3,
    ) -> int:
        """
        Ask the LLM how many FAQs are appropriate for the document content.

        Returns an integer between min_faqs and max_faqs (inclusive).
        """
        max_faqs = min(max_faqs, self.max_faqs)
        min_faqs = max(min_faqs, self.min_faqs)

        max_content_length = 6000
        truncated = content
        if len(content) > max_content_length:
            truncated = content[:max_content_length] + "\n... (truncated)"

        word_count = len(truncated.split())
        prompt = (
            "You are an expert at analyzing documents for FAQ generation.\n"
            f"Given the document below ({word_count} words), decide how many "
            f"high-quality FAQ pairs should be generated.\n"
            f"Return ONLY a single integer between {min_faqs} and {max_faqs}.\n"
            "Use fewer FAQs for short or simple documents and more for long, "
            "detailed, or multi-topic documents.\n\n"
            f"Document content:\n{truncated}\n\n"
            "Number of FAQs:"
        )

        try:
            logger.info("Determining optimal FAQ count from document content")
            response = self.llm.invoke(prompt)
            response_text = (
                response.content if hasattr(response, "content") else str(response)
            )
            match = re.search(r"\d+", response_text.strip())
            if match:
                count = int(match.group())
                return max(min_faqs, min(count, max_faqs))
        except Exception as exc:
            logger.warning("FAQ count determination failed, using heuristic: %s", exc)

        if word_count < 500:
            return min_faqs
        if word_count < 2000:
            return min(10, max_faqs)
        if word_count < 5000:
            return min(20, max_faqs)
        return max_faqs

    async def generate_faqs(
        self,
        content: str,
        num_faqs: int = 10,
        language: str = "English",
    ) -> List[Dict[str, any]]:
        """
        Generate FAQs from document content using LLM.

        Args:
            content: The extracted document content
            num_faqs: Number of FAQs to generate
            language: Language to generate FAQs in

        Returns:
            List of FAQ dictionaries with 'question', 'answer', 'confidence_score'
        """
        try:
            # Truncate content if too long to avoid token limits
            max_content_length = 8000
            if len(content) > max_content_length:
                content = content[:max_content_length] + "\n... (truncated)"

            # Create the prompt for FAQ generation
            faq_prompt = ChatPromptTemplate.from_template(
                """You are an expert at creating frequently asked questions (FAQs) from documents.

Given the following document content, generate exactly {num_faqs} important and relevant FAQs that a reader would likely ask.

Requirements:
1. Generate exactly {num_faqs} Q&A pairs (no more, no less)
2. Each question should be clear and concise (under 100 words)
3. Each answer should be informative and based directly on the content (under 200 words)
4. Include a confidence score (0.0-1.0) indicating how confident you are in the answer's accuracy based on the content
5. Focus on practical and frequently asked questions
6. Write ALL questions and answers in {language} only

Format your response EXACTLY as valid JSON array like this (no markdown, no extra text):
[
  {{"question": "What is...", "answer": "...", "confidence_score": 0.95}},
  {{"question": "How do...", "answer": "...", "confidence_score": 0.90}}
]

Document content:
{content}

Generate {num_faqs} FAQs now:"""
            )

            # Format the prompt with the content
            prompt = faq_prompt.format(
                content=content,
                num_faqs=num_faqs,
                language=language,
            )

            # Call LLM to generate FAQs
            logger.info(f"Generating {num_faqs} FAQs from document content")
            response = self.llm.invoke(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)

            # Parse the JSON response
            faqs = self._parse_faq_response(response_text, num_faqs)

            logger.info(f"Successfully generated {len(faqs)} FAQs")
            return faqs

        except Exception as e:
            logger.error(f"Error generating FAQs: {str(e)}", exc_info=True)
            raise

    def _parse_faq_response(self, response: str, expected_count: int) -> List[Dict[str, any]]:
        """
        Parse LLM response to extract FAQs.

        Args:
            response: The raw LLM response
            expected_count: Expected number of FAQs

        Returns:
            List of parsed FAQs
        """
        try:
            # Try to extract JSON from the response
            # LLM might include extra text before/after the JSON
            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if not json_match:
                logger.warning("No JSON array found in LLM response")
                return self._create_fallback_faqs(response, expected_count)

            json_str = json_match.group(0)
            faqs_data = json.loads(json_str)

            # Validate and clean the FAQs
            valid_faqs = []
            for item in faqs_data:
                if isinstance(item, dict) and "question" in item and "answer" in item:
                    faq = {
                        "question": sanitize_text(str(item.get("question", ""))).strip(),
                        "answer": sanitize_text(str(item.get("answer", ""))).strip(),
                        "confidence_score": float(item.get("confidence_score", 0.85)),
                    }

                    # Validate question and answer are not empty
                    if faq["question"] and faq["answer"]:
                        valid_faqs.append(faq)

            if not valid_faqs:
                logger.warning("No valid FAQs extracted from response")
                return self._create_fallback_faqs(response, expected_count)

            return valid_faqs[:expected_count]

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse FAQ JSON: {str(e)}")
            return self._create_fallback_faqs(response, expected_count)

    def _create_fallback_faqs(
        self, content: str, num_faqs: int
    ) -> List[Dict[str, any]]:
        """
        Create fallback FAQs if LLM generation fails.
        Extracts simple Q&A patterns from content.

        Args:
            content: The document content
            num_faqs: Number of FAQs to create

        Returns:
            List of basic FAQs
        """
        fallback_faqs = []

        # Simple heuristic: extract first few sentences as FAQs
        sentences = re.split(r"[.!?]\s+", content)[:num_faqs]

        for i, sentence in enumerate(sentences, 1):
            if len(sentence.strip()) > 10:
                fallback_faqs.append(
                    {
                        "question": f"What is discussed in section {i}?",
                        "answer": sentence.strip()[:200],
                        "confidence_score": 0.5,
                    }
                )

        if not fallback_faqs:
            # Last resort: create a generic FAQ
            fallback_faqs.append(
                {
                    "question": "What is this document about?",
                    "answer": content[:200],
                    "confidence_score": 0.3,
                }
            )

        return fallback_faqs[:num_faqs]

    def validate_faq(self, question: str, answer: str) -> Tuple[bool, str]:
        """
        Validate FAQ quality.

        Args:
            question: FAQ question
            answer: FAQ answer

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not question or len(question.strip()) < 5:
            return False, "Question must be at least 5 characters"

        if not answer or len(answer.strip()) < 10:
            return False, "Answer must be at least 10 characters"

        if len(question) > 500:
            return False, "Question must not exceed 500 characters"

        if len(answer) > 5000:
            return False, "Answer must not exceed 5000 characters"

        return True, ""


# Singleton instance
_faq_generator_instance = None


def get_faq_generator() -> FAQGeneratorService:
    """Get singleton instance of FAQ generator"""
    global _faq_generator_instance
    if _faq_generator_instance is None:
        _faq_generator_instance = FAQGeneratorService()
    return _faq_generator_instance
