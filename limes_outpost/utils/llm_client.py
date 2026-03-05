import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        # Cerebras provides an OpenAI-compatible SDK
        # We point it to the Cerebras URL and use your CEREBRAS_API_KEY
        self.api_key = os.getenv("CEREBRAS_API_KEY")
        self.client = OpenAI(
            base_url="https://api.cerebras.ai/v1",
            api_key=self.api_key
        )

    def generate(self, system_prompt, user_prompt, model="llama3.1-8b", json_mode=True):
        """Sends a request to Cerebras and returns the text response."""
        if not self.api_key:
            print("❌ [LLM ERROR]: CEREBRAS_API_KEY not found in .env")
            return None

        # Determine the response format based on the json_mode toggle
        format_setting = {"type": "json_object"} if json_mode else {"type": "text"}

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                # Temperature 0.2 for more consistent, structured JSON
                temperature=0.2,
                response_format=format_setting
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ [CEREBRAS API ERROR]: {e}")
            return None

    def ask_structured(self, system_prompt, user_prompt):
        """
        Legacy wrapper to maintain compatibility with older agent code 
        if they still call 'ask_structured'.
        """
        result = self.generate(system_prompt, user_prompt, json_mode=True)
        return json.loads(result) if result else None