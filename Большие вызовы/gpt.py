from g4f.client import Client
import logging

class Dialog:
    def __init__(self, messages: list = None):
        self.client = Client()
        if messages:
            self.messages = messages
        if not messages:
            self.messages = list()
            self.messages.append({"role": "system", "content": "You are an assistant."})

    def ask(self, message: str) -> str:
        try:
            self.messages.append({"role": "user", "content": message})
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=self.messages)
            answer = response.choices[0].message.content
            self.messages.append({"role": "assistant", "content": answer})
            return answer
        except Exception as e:
            logging.error(f"Ошибка при запросе к GPT: {e}", exc_info=True)
            return "Произошла ошибка при обращении к языковой модели."

    def ask_once(self, message):
        try:
            if type(message) == str:
                message_gpt = [{"role": "user", "content": message}]
            else:
                message_gpt = message
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=message_gpt)
            answer = response.choices[0].message.content
            return answer
        except Exception as e:
            logging.error(f"Ошибка при запросе к GPT (ask_once): {e}", exc_info=True)
            return "Произошла ошибка при обращении к языковой модели."

    def clear_messages(self):
        self.messages.clear()
        self.messages.append({"role": "system", "content": "You are an assistant."})
        return self.messages