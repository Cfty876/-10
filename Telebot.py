from telebot import TeleBot, types
from PIL import Image, ImageEnhance
import os
import io
import msg_saver
from gpt import Dialog
from models import load_model
from transformers import pipeline
from googletrans import Translator
import asyncio
import logging
import torch

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TOKEN = ''
bot = TeleBot(TOKEN)
gpt_dialog = Dialog()
try:
    if os.path.exists('light_model.pkl'):
        os.remove('light_model.pkl')
    image_model = load_model()
except Exception as e:
    logging.error(f"Ошибка при загрузке модели: {e}", exc_info=True)
    print(f"Ошибка при загрузке модели: {e}")
    image_model = None 
IS_RUNNING = False

# --- СПИСОК ИЗБРАННОГО ---
favorites = {}  # user_id: [recipe_name]

# --- Transformers pipeline ---
image_to_text = pipeline("image-to-text", model="Salesforce/blip-image-captioning-base")

# --- Translator ---
translator = Translator()

# --- Inline keyboard для выбора генерации изображения ---
def generate_image_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="Да, сгенерировать изображение", callback_data="generate_image"))
    keyboard.add(types.InlineKeyboardButton(text="Нет, только рецепт", callback_data="no_image"))
    return keyboard

@bot.callback_query_handler(func=lambda call: call.data in ["generate_image", "no_image"])
def handle_image_choice(call):
    user_id = call.message.chat.id
    generate_image_flag = call.data == "generate_image"
    bot.delete_message(user_id, call.message.message_id)  # Удаляем inline keyboard

    user_messages = msg_saver.get_messages(user_id)
    if user_messages and len(user_messages) > 1:
        last_user_message = user_messages[-1]["content"]
        generate_recipe(user_id, last_user_message, generate_image_flag)  # Передаем флаг
    else:
        bot.send_message(user_id, "Пожалуйста, отправьте запрос на рецепт сначала.", reply_markup=create_markup())

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    start_message(message.from_user.id)

@bot.message_handler(func=lambda message: message.text == "Случайный ингредиент")
def random_ingredient(message):
    ingredient = gpt_dialog.ask_once("Назови один случайный ингредиент для еды.")
    bot.send_message(message.chat.id, f"Случайный ингредиент: {ingredient}", reply_markup=create_markup())

@bot.message_handler(func=lambda message: message.text == "Случайное блюдо")
def random_dish(message):
    dish = gpt_dialog.ask_once("Назови одно случайное блюдо.")
    bot.send_message(message.chat.id, f"Случайное блюдо: {dish}", reply_markup=create_markup())

@bot.message_handler(func=lambda message: message.text == "Избранное")
def show_favorites(message):
    user_id = message.from_user.id
    if user_id in favorites and favorites[user_id]:
        bot.send_message(message.chat.id, "Ваши избранные рецепты:\n" + "\n".join(favorites[user_id]),
                         reply_markup=create_markup())
    else:
        bot.send_message(message.chat.id, "У вас пока нет избранных рецептов.", reply_markup=create_markup())

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.send_message(message.chat.id, "Получено фото, начинаю анализ...")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        image = Image.open(io.BytesIO(downloaded_file))
        description = image_to_text(image)[0]['generated_text']

        # Перевод текста
        translated = translator.translate(description, dest='ru')
        translated_text = translated.text

        bot.send_message(message.chat.id, f"{translated_text}")

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка анализа: {e}")

    bot.send_message(message.chat.id, "Чем еще могу помочь?", reply_markup=create_markup())

# --- ОБРАБОТКА ДОБАВЛЕНИЯ В ИЗБРАННОЕ ---
def add_to_favorites(user_id, recipe_name):
    if user_id not in favorites:
        favorites[user_id] = []
    if recipe_name not in favorites[user_id]:
        favorites[user_id].append(recipe_name)
        return True
    else:
        return False

# --- ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ---
@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    global IS_RUNNING
    print_user(message)
    user_id = message.from_user.id

    if message.text.startswith("+избранное"):
        recipe_name = message.text[len("+избранное"):].strip()
        if add_to_favorites(user_id, recipe_name):
            bot.send_message(user_id, f"Рецепт '{recipe_name}' добавлен в избранное!", reply_markup=create_markup())
        else:
            bot.send_message(user_id, f"Рецепт '{recipe_name}' уже есть в избранном!", reply_markup=create_markup())
        IS_RUNNING = False
        return

    if IS_RUNNING:
        bot.send_message(user_id, 'В данный момент бот занят', reply_markup=create_markup())
        return

    IS_RUNNING = True
    try:
        user_messages = msg_saver.get_messages(user_id)
        if message.text == 'КотелОК вари!':
            if user_messages is not None: 
                gpt_dialog.messages = user_messages
                gpt_dialog.clear_messages()
                msg_saver.save_messages(user_id, gpt_dialog.messages)
            start_message(user_id)
            return
        bot.send_message(user_id, "Хотите сгенерировать изображение для рецепта?", reply_markup=generate_image_keyboard())

        msg_saver.save_messages(user_id, gpt_dialog.messages + [{"role": "user", "content": message.text}])

    finally:
        IS_RUNNING = False

def generate_recipe(user_id, user_message, generate_image_flag):
    try:
        ans = gpt_dialog.ask('Привет, я нейросеть - КотелОК! Придумай блюдо или ингредиенты к блюду и я составлю рецепт к нему: ' + user_message)
        print(ans)
        bot.send_message(user_id, ans, reply_markup=create_markup())

        # Добавляем возможность добавить в избранное после получения рецепта
        bot.send_message(user_id, "Если хотите добавить рецепт в избранное, напишите: +избранное НазваниеРецепта(скопировать сообщение)")

        if generate_image_flag:
            prompt = gpt_dialog.ask_once('Какое краткое название блюда на английском языке: ' + ans)
            print(prompt)
            msq_wait = bot.send_message(user_id, 'Генерирую изображение...')  
            try:
                if image_model:  # Проверяем, что модель загружена
                    image = generate_image(prompt)
                    bot.delete_message(user_id, msq_wait.message_id)  # Используем message_id
                    if image:  
                        with open('image.png', 'rb') as photo:
                            bot.send_photo(user_id, photo=photo)
                    else:
                        bot.send_message(user_id, "Не удалось сгенерировать изображение.")

                else:
                    bot.delete_message(user_id, msq_wait.message_id)
                    bot.send_message(user_id, "Невозможно сгенерировать изображение, модель не загружена.")

            except Exception as e:
                logging.error(f"Ошибка при генерации изображения: {e}", exc_info=True)
                bot.delete_message(user_id, msq_wait.message_id) 
                bot.send_message(user_id, f"Ошибка при генерации изображения: {e}")
        else:
            bot.send_message(user_id, "Генерация изображения отменена.")

        msg_saver.save_messages(user_id, gpt_dialog.messages)

    except Exception as e:
        logging.error(f"Ошибка при генерации рецепта: {e}", exc_info=True)
        bot.send_message(user_id, f"Ошибка при генерации рецепта: {e}")

def print_user(message):
    print(f'{message.from_user.full_name} [@{message.from_user.username}]: {message.text}')

def create_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_new = types.KeyboardButton('КотелОК вари!')
    btn_random_ingredient = types.KeyboardButton("Случайный ингредиент")
    btn_random_dish = types.KeyboardButton("Случайное блюдо")
    btn_favorites = types.KeyboardButton("Избранное")
    # NO BUTTON - send photo
    markup.add(btn_new)
    markup.add(btn_random_ingredient, btn_random_dish)
    markup.add(btn_favorites)
    return markup

def start_message(user_id):
    bot.send_message(user_id,
                     'КотелОК - твой личный кулинарный ИИ! Отправь мне название блюда или ингридиентов или\n'
                     'отправьте фото ингридиента или блюда, чтобы проанализировать, или выберите действие:',
                     reply_markup=create_markup())

def improve_image(image: Image.Image, path: str):
    # Увеличение резкости
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2)
    image = image.convert('RGB')

    # Сохранение улучшенного изображения
    image.save(path, "PNG")
    return image

def generate_image(text):
    try:
        with torch.no_grad():
            prompt = f"{text}, food, high quality, realistic, detailed"
            image = image_model.generate_image(
                text=prompt,
                seed=-1,
                grid_size=1,
                is_seamless=True
            )
            save_image(image, 'image.png')

            # Post-processing
            image = Image.open('image.png') 
            image = improve_image(image, 'image.png') #улучшаем

            return 'image.png'  
    except Exception as e:
        logging.error(f"Ошибка при генерации изображения: {e}", exc_info=True)
        print(f"Ошибка при генерации изображения: {e}")
        return None

def save_image(image: Image.Image, path: str):
    if os.path.isdir(path):
        path = os.path.join(path, 'generated.png')
    elif not path.endswith('.png'):
        path += '.png'
    print("saving image to", path)
    image.save(path)
    image.close()  
    return

if __name__ == '__main__':
    try:
        bot.polling(none_stop=True, interval=0)
    finally:
        bot.stop_polling()
        asyncio.get_event_loop().close()
