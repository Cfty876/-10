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
import emoji

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TOKEN = ''
bot = TeleBot(TOKEN)
gpt_dialog = Dialog()
try:
    image_model = load_model()
except Exception as e:
    logging.error(f"Ошибка при загрузке модели: {e}", exc_info=True)
    print(f"Ошибка при загрузке модели: {e}")
    image_model = None
IS_RUNNING = False

# --- СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЯ ---
user_states = {}  # user_id: state
user_data = {}  # user_id: {height: , weight: , allergies: , preferences: , profile_filled: True/False}

# --- СПИСОК ИЗБРАННОГО ---
favorites = {}  # user_id: [recipe_name]

# --- Transformers pipeline ---
image_to_text = pipeline("image-to-text", model="Salesforce/blip-image-captioning-base")

# --- Translator ---
translator = Translator()


# --- Inline keyboard для выбора генерации изображения ---
def generate_image_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text=emoji.emojize("✅ Да, сгенерировать изображение"),
                                            callback_data="generate_image"))
    keyboard.add(types.InlineKeyboardButton(text=emoji.emojize("🚫 Нет, только рецепт"), callback_data="no_image"))
    return keyboard


@bot.callback_query_handler(func=lambda call: call.data in ["generate_image", "no_image"])
def handle_image_choice(call):
    user_id = call.message.chat.id
    generate_image_flag = call.data == "generate_image"
    bot.delete_message(user_id, call.message.message_id)

    user_messages = msg_saver.get_messages(user_id)
    if user_messages and len(user_messages) > 1:
        last_user_message = user_messages[-1]["content"]
        generate_recipe(user_id, last_user_message, generate_image_flag)
    else:
        bot.send_message(user_id, emoji.emojize("Пожалуйста, отправьте запрос на рецепт сначала. 📝"),
                         reply_markup=create_markup())


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    start_message(user_id)


@bot.message_handler(func=lambda message: message.text == emoji.emojize("🎲 Случайный ингредиент"))
def random_ingredient(message):
    ingredient = gpt_dialog.ask_once("Назови один случайный ингредиент для еды.")
    bot.send_message(message.chat.id, f"{emoji.emojize('✨ Случайный ингредиент: ')} {ingredient}",
                     reply_markup=create_markup())


@bot.message_handler(func=lambda message: message.text == emoji.emojize("🍽 Случайное блюдо"))
def random_dish(message):
    dish = gpt_dialog.ask_once("Назови одно случайное блюдо.")
    bot.send_message(message.chat.id, f"{emoji.emojize('✨ Случайное блюдо: ')} {dish}", reply_markup=create_markup())


@bot.message_handler(func=lambda message: message.text == emoji.emojize("❤️ Избранное"))
def show_favorites(message):
    user_id = message.from_user.id
    if user_id in favorites and favorites[user_id]:
        bot.send_message(message.chat.id, f"{emoji.emojize('🌟 Ваши избранные рецепты:\n')}" + "\n".join(favorites[user_id]),
                         reply_markup=create_markup())
    else:
        bot.send_message(message.chat.id, emoji.emojize("💔 У вас пока нет избранных рецептов. 😔"),
                         reply_markup=create_markup())


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.send_message(message.chat.id, emoji.emojize("🖼️ Получено фото, начинаю анализ... 🔎"))
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        image_stream = io.BytesIO(downloaded_file)  # Use BytesIO to handle image data in memory
        image = Image.open(image_stream).convert("RGB") # Ensure image is in RGB format

        description = image_to_text(image)[0]['generated_text']  # Получаем описание изображения

        translated = translator.translate(description, dest='ru')
        translated_text = translated.text

        bot.send_message(message.chat.id, f"{emoji.emojize('💡 Описание: ')}{translated_text}")

    except Exception as e:
        logging.exception("Ошибка при анализе изображения:")  # Log the full exception
        bot.send_message(message.chat.id, f"{emoji.emojize('❗ Ошибка анализа: ')}{e}")

    bot.send_message(message.chat.id, emoji.emojize("Чем еще могу помочь? 😊"), reply_markup=create_markup())


# --- ОБРАБОТКА ДОБАВЛЕНИЯ В ИЗБРАННОЕ ---
def add_to_favorites(user_id, recipe_name):
    if user_id not in favorites:
        favorites[user_id] = []
    if recipe_name not in favorites[user_id]:
        favorites[user_id].append(recipe_name)
        return True
    else:
        return False


# --- ОБРАБОТКА ОПРОСА ---
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_height")
def get_height(message):
    user_id = message.from_user.id
    try:
        height = int(message.text)
        if height < 50 or height > 250:
            bot.send_message(user_id, emoji.emojize("🤨 Похоже, вы ошиблись. Введите реальный рост в сантиметрах (от 50 до 250):"))
            return
        user_data[user_id]["height"] = height
        bot.send_message(user_id, emoji.emojize("🏋️ Отлично! Теперь укажите ваш вес в килограммах:"))
        user_states[user_id] = "waiting_for_weight"
    except ValueError:
        bot.send_message(user_id, emoji.emojize("🔢 Пожалуйста, введите числовое значение для вашего роста."))


@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_weight")
def get_weight(message):
    user_id = message.from_user.id
    try:
        weight = int(message.text)
        if weight < 10 or weight > 500:
            bot.send_message(user_id, emoji.emojize("🤔 Что-то не так. Введите реальный вес в килограммах (от 10 до 500):"))
            return
        user_data[user_id]["weight"] = weight
        bot.send_message(user_id, emoji.emojize("🍎 Прекрасно! Есть ли у вас какие-либо аллергии или пищевые непереносимости? (Например, лактоза, глютен)"))
        user_states[user_id] = "waiting_for_allergies"
    except ValueError:
        bot.send_message(user_id, emoji.emojize("🔢 Пожалуйста, введите числовое значение для вашего веса."))


@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_allergies")
def get_allergies(message):
    user_id = message.from_user.id
    allergies = message.text
    user_data[user_id]["allergies"] = allergies
    bot.send_message(user_id, emoji.emojize("🌱 И последнее: укажите ваши пищевые предпочтения (например, вегетарианство, кето, без сахара):"))
    user_states[user_id] = "waiting_for_preferences"


@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_preferences")
def get_preferences(message):
    user_id = message.from_user.id
    preferences = message.text
    user_data[user_id]["preferences"] = preferences
    user_data[user_id]["profile_filled"] = True
    bot.send_message(user_id, emoji.emojize(
        "🎉 Спасибо за предоставленную информацию! Теперь я лучше понимаю ваши потребности. Нажмите 'КотелОК вари!' чтобы начать готовить! 🍳"),
                     reply_markup=create_markup())
    user_states[user_id] = None


# --- ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ---
@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    global IS_RUNNING
    print_user(message)
    user_id = message.from_user.id

    if message.text.startswith("+избранное"):
        recipe_name = message.text[len("+избранное"):].strip()
        if add_to_favorites(user_id, recipe_name):
            bot.send_message(user_id,
                             f"{emoji.emojize('✅ Рецепт')} '{recipe_name}' {emoji.emojize('добавлен в избранное! ❤️')}",
                             reply_markup=create_markup())
        else:
            bot.send_message(user_id,
                             f"{emoji.emojize('ℹ️ Рецепт')} '{recipe_name}' {emoji.emojize('уже есть в избранном! ❤️')}",
                             reply_markup=create_markup())
        IS_RUNNING = False
        return

    if IS_RUNNING:
        bot.send_message(user_id, emoji.emojize('⏳ В данный момент бот занят, пожалуйста, подождите. 🧘'),
                         reply_markup=create_markup())
        return

    IS_RUNNING = True
    try:
        user_messages = msg_saver.get_messages(user_id)
        if message.text == emoji.emojize('🍳 КотелОК вари!'):
            if user_messages is not None:
                gpt_dialog.messages = user_messages
                gpt_dialog.clear_messages()
                msg_saver.save_messages(user_id, gpt_dialog.messages)
            handle_kotelok_vari(message)
            return

        bot.send_message(user_id, emoji.emojize("✨ Хотите сгенерировать изображение для рецепта? 🖼️"),
                         reply_markup=generate_image_keyboard())

        msg_saver.save_messages(user_id, gpt_dialog.messages + [{"role": "user", "content": message.text}])

    finally:
        IS_RUNNING = False


def generate_recipe(user_id, user_message, generate_image_flag):
    try:
        prompt = f"Придумай подробный рецепт блюда на основе следующих ингредиентов или названия: '{user_message}'.  Включи список ингредиентов, точные измерения и пошаговые инструкции по приготовлению.  Избегай двусмысленности и убедись, что рецепт понятен и легок в исполнении."

        if user_id in user_data and user_data[user_id].get("profile_filled"):
            prompt += f" Учитывай следующие предпочтения пользователя: рост - {user_data[user_id]['height']} см, вес - {user_data[user_id]['weight']} кг, аллергии - {user_data[user_id]['allergies']}, пищевые предпочтения - {user_data[user_id]['preferences']}."

        ans = gpt_dialog.ask(prompt)
        print(ans)
        bot.send_message(user_id, ans, reply_markup=create_markup())
        bot.send_message(user_id, emoji.emojize(
            "✍️ Если хотите добавить рецепт в избранное, напишите: +избранное НазваниеРецепта(скопировать сообщение) ❤️"))

        if generate_image_flag:
            prompt = gpt_dialog.ask_once('Какое краткое название блюда на английском языке: ' + ans)
            print(prompt)
            msq_wait = bot.send_message(user_id, emoji.emojize('⏳ Генерирую изображение... 🎨'))
            try:
                if image_model:
                    image = generate_image(prompt)
                    bot.delete_message(user_id, msq_wait.message_id)
                    if image:
                        with open('image.png', 'rb') as photo:
                            bot.send_photo(user_id, photo=photo)
                    else:
                        bot.send_message(user_id, emoji.emojize("⚠️ Не удалось сгенерировать изображение. 😔"))

                else:
                    bot.delete_message(user_id, msq_wait.message_id)
                    bot.send_message(user_id, emoji.emojize("❗ Невозможно сгенерировать изображение, модель не загружена. 😔"))

            except Exception as e:
                logging.error(f"Ошибка при генерации изображения: {e}", exc_info=True)
                bot.delete_message(user_id, msq_wait.message_id)
                bot.send_message(user_id, f"{emoji.emojize('❗ Ошибка при генерации изображения: ')}{e}")
        else:
            bot.send_message(user_id, emoji.emojize("🚫 Генерация изображения отменена. 🎨"))

        msg_saver.save_messages(user_id, gpt_dialog.messages)

    except Exception as e:
        logging.error(f"Ошибка при генерации рецепта: {e}", exc_info=True)
        bot.send_message(user_id, f"{emoji.emojize('❗ Ошибка при генерации рецепта: ')}{e}")


def print_user(message):
    print(f'{message.from_user.full_name} [@{message.from_user.username}]: {message.text}')


def create_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_new = types.KeyboardButton(emoji.emojize('🍳 КотелОК вари!'))
    btn_random_ingredient = types.KeyboardButton(emoji.emojize("🎲 Случайный ингредиент"))
    btn_random_dish = types.KeyboardButton(emoji.emojize("🍽 Случайное блюдо"))
    btn_favorites = types.KeyboardButton(emoji.emojize("❤️ Избранное"))

    markup.add(btn_new)
    markup.add(btn_random_ingredient, btn_random_dish)
    markup.add(btn_favorites)
    return markup


def start_message(user_id):
    # Keyboard
    keyboard = types.InlineKeyboardMarkup()
    if user_id not in user_data or not user_data[user_id].get("profile_filled"):
        keyboard.add(types.InlineKeyboardButton(text=emoji.emojize("📝 Заполнить анкету"), callback_data="fill_profile"))

    bot.send_message(user_id,
                     emoji.emojize("🎉 Добро пожаловать в *КотелОК*! 🎉\n\n"
                                   "Я - твой личный кулинарный ИИ 🤖🍳, и я здесь, чтобы сделать твою жизнь на кухне проще, "
                                   "интереснее и вкуснее!\n\n"
                                   "Со мной ты можешь:\n"
                                   "✨ Получать рецепты по *названию блюда* (например, 'борщ', 'паста карбонара')\n"
                                   "✨ Генерировать рецепты на основе *имеющихся ингредиентов* (просто перечисли их!)\n"
                                   "✨ Загружать *фотографии* продуктов, и я предложу, что из них приготовить!\n"
                                   "✨ Открывать для себя *случайные ингредиенты и блюда* для вдохновения\n"
                                   "✨ Сохранять любимые рецепты в *Избранное*, чтобы всегда иметь их под рукой\n\n"
                                   f"{'Чтобы начать, мне нужно немного узнать о тебе. Пожалуйста, заполни небольшую анкету:' if user_id not in user_data or not user_data[user_id].get('profile_filled') else 'Теперь можно начать! Нажмите КотелОК вари!'}") + emoji.emojize(
                         " 😊"),
                     parse_mode="Markdown",
                     reply_markup=keyboard if user_id not in user_data or not user_data[user_id].get(
                         "profile_filled") else create_markup())  # Изменено


def handle_kotelok_vari(message):
    user_id = message.from_user.id

    if user_id not in user_data or not user_data[user_id].get("profile_filled"):
        bot.send_message(user_id, emoji.emojize(
            "📝 Пожалуйста, заполните анкету, чтобы я мог предложить вам наилучшие рецепты! Нажмите /start 🚀"),
                         reply_markup=create_markup())
        return

    bot.send_message(user_id, emoji.emojize(
        "✨ Отлично! Теперь отправьте мне ингредиенты, которые у вас есть, меню которое надо составить или название блюда, которое хотите приготовить. ✍️"))


@bot.callback_query_handler(func=lambda call: call.data == "fill_profile")
def fill_profile(call):
    user_id = call.message.chat.id
    bot.delete_message(user_id, call.message.message_id)
    user_data[user_id] = {}
    bot.send_message(user_id, emoji.emojize("📏 Для начала, укажите ваш рост в сантиметрах:"))
    user_states[user_id] = "waiting_for_height"


def improve_image(image: Image.Image, path: str):
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.5)
    image = image.convert('RGB')
    image.save(path, "PNG")
    return image


def generate_image(text):
    try:
        with torch.no_grad():
            prompt = f"{text}, высокое качество, реалистичный, детализированный, 8k, 4k, studio lighting, food photography"
            image = image_model.generate_image(
                text=prompt,
                seed=-1,
                grid_size=1,
                is_seamless=True
            )
            save_image(image, 'image.png')

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
        asyncio.run(bot.close())