from min_dalle import MinDalle
from pickle import dump, load
import logging
import torch

model_file = 'light_model.pkl'


def create_model(file_name=model_file):
    try:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logging.info(f"Используемое устройство: {device}")

        model = MinDalle(
            models_root='./pretrained',
            is_mega=False,
            is_reusable=True,
            device=device
        )

        with open(file_name, 'wb') as file:
            dump(model, file)
        logging.info(f"Модель сохранена в файл: {file_name}")
        return model
    except Exception:
        logging.exception("Ошибка при создании модели:")
        return None


def load_model(file_name=model_file):
    try:
        try:
            with open(file_name, 'rb') as file:
                model = load(file)
            logging.info(f"Модель успешно загружена из файла: {file_name}")
            return model
        except FileNotFoundError:
            logging.warning(f"Файл модели не найден: {file_name}. Создание новой модели.")
            model = create_model(file_name)
            return model
        except Exception:
            logging.exception("Ошибка при загрузке модели из файла:")
            return None
    except Exception:
        logging.exception("Критическая ошибка при загрузке модели:")
        return None