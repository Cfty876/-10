from telebot import TeleBot, types
from PIL import Image
import os
import io
import msg_saver
from gpt import Dialog
from models import load_model
from transformers import pipeline
from googletrans import Translator

TOKEN = ''
bot = TeleBot(TOKEN)
gpt_dialog = Dialog()
image_model = load_model()
IS_RUNNING = False

# --- СПИСОК ИЗБРАННОГО (замените на базу данных) ---
favorites = {}  # user_id: [recipe_name]

# --- Transformers pipeline ---
image_to_text = pipeline("image-to-text", model="Salesforce/blip-image-captioning-base")

# --- Translator ---
translator = Translator()

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
        bot.send_message(message.chat.id, "Ваши избранные рецепты:\n" + "\n".join(favorites[user_id]), reply_markup=create_markup())
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

# --- ОБРАБОТКА ДОБАВЛЕНИЯ В ИЗБРАННОЕ (пример) ---
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

    # Обработка добавления в избранное (пример)
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
    user_messages = msg_saver.get_messages(user_id)

    if message.text == 'КотелОК вари!':
        if user_messages is not None:  # очистка предыдущих сообщений
            gpt_dialog.messages = user_messages
            gpt_dialog.clear_messages()
            msg_saver.save_messages(user_id, user_messages)
        start_message(user_id)
        IS_RUNNING = False
        return

    if user_messages is None or len(user_messages) == 1:  # Первое сообщение не уточняющее

        ans = gpt_dialog.ask('Привет, я нейросеть - КотелОК! Придумай блюдо или ингредиенты к блюду и я составлю рецепт к нему: ' + message.text)
        print(ans)
        bot.send_message(user_id, ans, reply_markup=create_markup())
        # Добавляем возможность добавить в избранное после получения рецепта
        bot.send_message(user_id, "Если хотите добавить рецепт в избранное, напишите: +избранное НазваниеРецепта")
        prompt = gpt_dialog.ask_once('Какое краткое название блюда на английском языке: ' + ans)
        print(prompt)
        msq_wait = bot.send_message(user_id, '')
        image = generate_image(prompt)
        bot.delete_message(user_id, msq_wait.id)
        bot.send_photo(user_id, photo=image)


    else:  # Уточняющее сообщение
        ans = gpt_dialog.ask(message.text)
        print(ans)
        bot.send_message(user_id, ans, reply_markup=create_markup())

    msg_saver.save_messages(user_id, gpt_dialog.messages)
    IS_RUNNING = False

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
                     'КотелОК - твой личный кулинарный ИИ!\n'
                     'Отправьте фото ингридиента или блюда, чтобы проанализировать, или выберите действие:',
                     reply_markup=create_markup())

def generate_image(text):
    image = image_model.generate_image(
        text=text,
        seed=-1,
        grid_size=1,
        is_seamless=True
    )
    save_image(image, 'image.png')
    return image

def save_image(image: Image.Image, path: str):
    if os.path.isdir(path):
        path = os.path.join(path, 'generated.png')
    elif not path.endswith('.png'):
        path += '.png'
    print("saving image to", path)
    image.save(path)
    return image

if __name__ == '__main__':
    bot.polling(none_stop=True, interval=0)
