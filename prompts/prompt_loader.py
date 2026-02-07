"""
Prompt Loader for Multilingual Support
Loads language-specific prompts from external files
"""
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Get the directory where this file is located
PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

class PromptLoader:
    """Loads and manages language-specific prompts"""
    
    def __init__(self):
        self.cache: Dict[str, str] = {}
    
    def load_prompt(self, prompt_type: str, language: str) -> Optional[str]:
        """
        Load a prompt from file
        
        Args:
            prompt_type: 'followup' or 'report'
            language: 'hi', 'ta', 'te', 'bn', 'kn', etc.
        
        Returns:
            Prompt text or None if not found
        """
        cache_key = f"{prompt_type}_{language}"
        
        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Build file path
        prompt_file = os.path.join(PROMPTS_DIR, prompt_type, f"{language}.txt")
        
        # Try to load from file
        try:
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt = f.read().strip()
                    # Cache it
                    self.cache[cache_key] = prompt
                    logger.info(f"✅ Loaded {language} {prompt_type} prompt from file ({len(prompt)} chars)")
                    return prompt
            else:
                # Enhanced error logging for production debugging
                prompt_dir = os.path.dirname(prompt_file)
                logger.error(f"❌ Prompt file not found: {prompt_file}")
                if os.path.exists(prompt_dir):
                    existing_files = os.listdir(prompt_dir)
                    logger.error(f"   Files in directory: {existing_files}")
                else:
                    logger.error(f"   Directory does not exist: {prompt_dir}")
                    logger.error(f"   PROMPTS_DIR: {PROMPTS_DIR}")
                    logger.error(f"   Current working directory: {os.getcwd()}")
                return None
        except Exception as e:
            logger.error(f"❌ Error loading prompt file {prompt_file}: {e}", exc_info=True)
            return None
    
    def clear_cache(self):
        """Clear the prompt cache (useful for hot-reloading)"""
        self.cache.clear()
        logger.info("🔄 Prompt cache cleared")


# Global instance
prompt_loader = PromptLoader()


def get_followup_prompt(language: str, **kwargs) -> Optional[str]:
    """
    Get follow-up question prompt for a language
    
    Args:
        language: Language code ('hi', 'ta', etc.)
        **kwargs: Variables to format into the prompt
    
    Returns:
        Formatted prompt or None
    """
    prompt_template = prompt_loader.load_prompt('followup', language)
    if prompt_template:
        try:
            return prompt_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing variable in prompt template: {e}")
            return None
    return None


def get_report_prompt(language: str, **kwargs) -> Optional[str]:
    """
    Get diagnosis report prompt for a language
    
    Args:
        language: Language code ('hi', 'ta', etc.)
        **kwargs: Variables to format into the prompt
    
    Returns:
        Formatted prompt or None
    """
    prompt_template = prompt_loader.load_prompt('report', language)
    if prompt_template:
        try:
            return prompt_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing variable in prompt template: {e}")
            return None
    return None


# Language metadata
SUPPORTED_LANGUAGES = {
    'en': {'name': 'English', 'native': 'English'},
    'hi': {'name': 'Hindi', 'native': 'हिंदी'},
    'ta': {'name': 'Tamil', 'native': 'தமிழ்'},
    'te': {'name': 'Telugu', 'native': 'తెలుగు'},
    'bn': {'name': 'Bengali', 'native': 'বাংলা'},
    'kn': {'name': 'Kannada', 'native': 'ಕನ್ನಡ'}
}


def is_language_supported(language: str, prompt_type: str = 'followup') -> bool:
    """Check if a language has prompt files available"""
    if language == 'en':
        return True  # English is always supported (default)
    
    prompt_file = os.path.join(PROMPTS_DIR, prompt_type, f"{language}.txt")
    return os.path.exists(prompt_file)


if __name__ == "__main__":
    # Test the prompt loader
    print("Testing Prompt Loader...")
    print("\nSupported Languages:", SUPPORTED_LANGUAGES)
    
    # Test Hindi follow-up
    print("\n" + "="*50)
    print("Testing Hindi Follow-up Prompt:")
    hindi_followup = get_followup_prompt(
        'hi',
        patient_context="30 साल, पुरुष",
        bmi_info="",
        symptoms_str="बुखार, खांसी",
        chat_history="कोई नहीं",
        question_count=0,
        next_question_number=1
    )
    if hindi_followup:
        print(hindi_followup[:200] + "...")
    
    # Test Tamil report
    print("\n" + "="*50)
    print("Testing Tamil Report Prompt:")
    tamil_report = get_report_prompt(
        'ta',
        age=30,
        gender_tamil="ஆண்",
        symptoms_str="காய்ச்சல், இருமல்",
        bmi_info="",
        chat_history="இல்லை",
        mapped_diseases="சளி"
    )
    if tamil_report:
        print(tamil_report[:200] + "...")
    
    # Check language support
    print("\n" + "="*50)
    print("Language Support Check:")
    for lang_code in ['en', 'hi', 'ta', 'te', 'bn', 'kn']:
        followup_supported = is_language_supported(lang_code, 'followup')
        report_supported = is_language_supported(lang_code, 'report')
        print(f"{lang_code}: Follow-up={followup_supported}, Report={report_supported}")






