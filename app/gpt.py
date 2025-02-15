from g4f.client import Client

class Dialog:
    def __init__(self, messages: list = None):
        self.client = Client()
        if messages:
            self.messages = messages
        if not messages:
            self.messages = list()
            self.messages.append({"role": "system", "content": "You are an assistant."})

    def ask(self, message: str) -> str:
        self.messages.append({"role": "user", "content": message})
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=self.messages)
        answer = response.choices[0].message.content
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    def ask_once(self, message):
         # Обратите ВНИМАНИЕ на этот метод!
        if isinstance(message, str):
            message_gpt = [{"role": "user", "content": message}]
        elif isinstance(message, list): # Добавлена обработка случая, когда передается список messages
            message_gpt = message
        else:
            raise ValueError("Message must be a string or a list of messages")
        response = self.client.chat.completions.create(
            model="gpt-4", # ВНИМАНИЕ: gpt-3.5-turbo не умеет анализировать изображения!
            messages=message_gpt)
        answer = response.choices[0].message.content
        return answer


    def clear_messages(self):
        self.messages.clear()
        self.messages.append({"role": "system", "content": "You are an assistant."})
        return self.messages