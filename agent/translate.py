from google.cloud import translate_v2 as translate


class Translator:
    """
    Translator provides functionality to detect the language of a given text
    and translate text between different languages using Google Cloud Translation API.
    """

    # Initialize the Google Translate client
    _translate_client = translate.Client()

    @classmethod
    def detect_language(cls, text):
        """
        Detects the language of the provided text using Google Cloud Translation API.

        Args:
            text (str or bytes): The text whose language needs to be detected.

        Returns:
            str: The detected language code (e.g., 'en' for English, 'es' for Spanish).
        """
        # Decode byte input to string if necessary
        if isinstance(text, bytes):
            text = text.decode("utf-8")

        # Use the API to detect the language
        result = cls._translate_client.detect_language(text)
        return result["language"]

    @classmethod
    def translate(cls, question, answer):
        """
        Translates the 'answer' text to the language of the 'question' text, if they differ.

        Args:
            question (str or bytes): The question text whose language determines the target language.
            answer (str or bytes): The answer text to potentially translate.

        Returns:
            tuple:
                - bool: True if translation was performed, False otherwise.
                - str: The translated text if translated, or the original answer if no translation was needed.
        """
        # Detect the language of both question and answer
        question_language = Translator.detect_language(question)
        answer_language = Translator.detect_language(answer)

        text = answer
        try:
            if question_language != answer_language:
                # Ensure input is in list format as required by the API
                if isinstance(text, bytes):
                    text = [text.decode("utf-8")]
                elif isinstance(text, str):
                    text = [text]

                # Translate the answer text to the question's language
                results = cls._translate_client.translate(
                    values=text,
                    target_language=question_language,
                    source_language=answer_language,
                )

                # Output diagnostic information for each result
                for result in results:
                    if "detectedSourceLanguage" in result:
                        print(
                            f"Detected source language: {result['detectedSourceLanguage']}"
                        )
                    print(f"Input text: {result['input']}")
                    print(f"Translated text: {result['translatedText']}")
                    print()

                return True, result["translatedText"]
        except:
            # If any error occurs during translation, skip and return original answer
            pass

        return question_language != answer_language, answer
