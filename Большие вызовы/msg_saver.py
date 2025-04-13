from os import path, makedirs
from pickle import dump, load
import logging

FOLDER = 'user_messages'


def get_messages(user_id: (int, str)):
    if type(user_id) is int:
        user_id = str(user_id)
    file_name = path.join(FOLDER, user_id)
    try:
        if not path.exists(file_name):
            return None
        with open(file_name, 'rb') as file:
            messages = load(file)
        return messages
    except Exception as e:
        logging.error(f"Ошибка при чтении сообщений пользователя {user_id}: {e}", exc_info=True)
        return None


def save_messages(user_id: (int, str), messages: list):
    if type(user_id) is int:
        user_id = str(user_id)
    file_name = path.join(FOLDER, user_id)
    try:
        if not path.exists(FOLDER):
            makedirs(FOLDER) # Создаем директорию, если ее нет
        with open(file_name, 'wb') as file:
            dump(messages, file)
    except Exception as e:
        logging.error(f"Ошибка при сохранении сообщений пользователя {user_id}: {e}", exc_info=True)

if __name__ == '__main__':
    # save_messages(123, [{1: 34, 3: 34}, {'324': '324'}])
    print(get_messages(1345005475))