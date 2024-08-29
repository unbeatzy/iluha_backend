import sqlite3
import re
import requests
import asyncio
import hashlib
import time
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from aiogram.types.message import ContentType
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from yoomoney import Client, Quickpay
from datetime import datetime

# Инициализация бота и диспетчера
API_TOKEN = 'bot_token'
ADMIN_ID = 'admin_id'
YOOMONEY_TOKEN = 'yoomoney_token'
YOOMONEY_WALLET = 'yoomoney_wallet'

bot = Bot(token=API_TOKEN)
client = Client(YOOMONEY_TOKEN)

# Инициализация хранилища состояний
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Подключение к базе данных
conn = sqlite3.connect('vpn_bot.db')
cursor = conn.cursor()

# Создание таблицы для ключей
cursor.execute('''CREATE TABLE IF NOT EXISTS vpn_keys
                 (id INTEGER PRIMARY KEY, key TEXT, duration INTEGER, is_used BOOLEAN)''')
conn.commit()

# Создание таблицы для пользователей
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, subscription_end_date TEXT)''')
conn.commit()

# Создание таблицы для выданных ключей
cursor.execute('''
    CREATE TABLE IF NOT EXISTS issued_keys
    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, payment_label TEXT, key TEXT, issued BOOLEAN, duration INTEGER)
''')
conn.commit()

# Состояния для ожидания данных от администратора
class AddKeysState(StatesGroup):
    waiting_for_keys = State()
    waiting_for_duration = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class PaymentState(StatesGroup):
    waiting_for_payment_method = State()
    waiting_for_payment_card = State()
    waiting_for_screenshot = State()

# Команда /start
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    # Сохранение пользователя в базе данных, если его еще нет
    cursor.execute('''INSERT OR IGNORE INTO users (id, username, first_name, last_name)
                      VALUES (?, ?, ?, ?)''', (user_id, username, first_name, last_name))
    conn.commit()

    # Клавиатура
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["💰 Купить", "ℹ️ Профиль", "🆘 Поддержка", "😻 Тестовый период", "🗒 Инструкция по подключению"]
    keyboard.add(*buttons)
    await message.answer("Привет! 👋\n\nbeatVPN - доступный VPN сервис для всех!\n\n❗️Обязательно подпишись на наш канал: @beatVPN_news\nТам ты сможешь быть в курсе всех новостей, а так же найдешь инструкцию по подключению❗️\n\nbeatVPN это:\n🤐 устойчивость к блокировкам;\n🚀 высокая скорость;\n🥳 доступ ко всем сайтам;\n💰 ниже средней цены по рынку.\n\nСтоимость: 150 рублей / 30 дней на одно устройство.\n\n❗️ Для новых пользователей доступен бесплатный тестовый период ❗️\n\n\nПожалуйста, выберите одно из действий ниже.", reply_markup=keyboard)

# Обработка нажатия кнопки "⬅️ Назад" для всех состояний
@dp.message_handler(lambda message: message.text == "⬅️ Назад", state='*')
async def go_back(message: types.Message, state: FSMContext):
    await state.finish()
    await send_welcome(message)

# Обработка нажатия кнопки "Купить"
@dp.message_handler(lambda message: message.text == "💰 Купить")
async def buy(message: types.Message):
    # Клавиатура
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["1 мес. (150 руб.)", "3 мес. (300 руб.)", "6 мес. (600 руб.)", "12 мес. (1200 руб.)", "⬅️ Назад"]
    keyboard.add(*buttons)
    await message.answer("🕘 Выберите срок подписки", reply_markup=keyboard)

# Обработка выбора срока подписки и способов оплаты
@dp.message_handler(lambda message: message.text in ["1 мес. (150 руб.)", "3 мес. (300 руб.)", "6 мес. (600 руб.)", "12 мес. (1200 руб.)"])
async def choose_payment_method(message: types.Message, state: FSMContext):
    duration_mapping = {
    "1 мес. (150 руб.)": (1, 2),
    "3 мес. (300 руб.)": (3, 300),
    "6 мес. (600 руб.)": (6, 600),
    "12 мес. (1200 руб.)": (12, 1200)
}
    duration, amount = duration_mapping[message.text]
    await state.update_data(duration=duration, amount=amount)

    # Клавиатура
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["💸 С карты на карту", "💳 Банковской картой", "⬅️ Назад"]
    keyboard.add(*buttons)
    await message.answer(f"Вы выбрали подписку на {duration} мес. Стоимость: {amount} руб.\n\nВыберите способ оплаты:", reply_markup=keyboard)
    await PaymentState.waiting_for_payment_method.set()

# Обработка нажатия кнопки "💸 С карты на карту"
@dp.message_handler(lambda message: message.text == "💸 С карты на карту", state=PaymentState.waiting_for_payment_method)
async def confirm_payment(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["✅ Подтвердить", "⬅️ Назад"]
    keyboard.add(*buttons)
    await PaymentState.waiting_for_screenshot.set()
    await message.answer("Реквизиты для оплаты:\n> Номер телефона для перевода по СБП: \n> Банк получателя: \n> Имя получателя: \n\n\n❗️После оплаты, пожалуйста, отправьте скриншот успешного перевода с суммой выбранной подписки ответным сообщением.❗️", reply_markup=keyboard, parse_mode="Markdown")

@dp.message_handler(state=PaymentState.waiting_for_screenshot, content_types=ContentType.PHOTO)
async def handle_screenshot(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    duration = data.get('duration')

    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"Пользователь @{message.from_user.username} отправил скриншот. Подтвердить платеж? Срок: {duration} мес.", reply_markup=admin_keyboard(user_id, duration))

    await state.finish()
    await message.answer("⏳ Пожалуйста, ожидайте. Администратор проверяет платеж.", reply_markup=main_menu())

@dp.message_handler(state=PaymentState.waiting_for_screenshot)
async def handle_invalid_content(message: types.Message, state: FSMContext):
    await message.answer("🖼 Пожалуйста, отправьте скриншот в виде изображения перевода средств из банковского приложения, где видно сумму и реквизиты перевода.")

def admin_keyboard(user_id, duration):
    keyboard = InlineKeyboardMarkup()
    confirm_button = InlineKeyboardButton(text="✅ Подтвердить платеж", callback_data=f"confirm_payment_{user_id}_{duration}")
    reject_button = InlineKeyboardButton(text="❌ Отклонить запрос", callback_data=f"reject_payment_{user_id}")
    keyboard.add(confirm_button, reject_button)
    return keyboard

@dp.callback_query_handler(lambda c: c.data.startswith('confirm_payment_') or c.data.startswith('reject_payment_'))
async def process_callback_admin(callback_query: types.CallbackQuery):
    data = callback_query.data.split('_')
    user_id = int(data[2])
    
    if 'confirm_payment' in callback_query.data:
        duration = int(data[3])
        cursor.execute('SELECT key FROM vpn_keys WHERE is_used = 0 AND duration = ? LIMIT 1', (duration,))
        key = cursor.fetchone()
        if key:
            cursor.execute('UPDATE vpn_keys SET is_used = 1 WHERE key = ?', (key[0],))
            conn.commit()
            
            keyboard = InlineKeyboardMarkup()
            instruction_button = InlineKeyboardButton(text="🗒 Инструкция по подключению", callback_data="instruction")
            keyboard.add(instruction_button)
            
            await bot.send_message(
                user_id,
                f"🥳 Ваш платеж подтвержден.\nВот ваш ключ на {duration} мес. 🔑: \n\n<code>{key[0]}</code>\n\n\n❗️❗️❗️Нажмите на ключ, чтобы скопировать его, и воспользуйтесь инструкцией по подключению, которая доступна по кнопке ниже.❗️❗️❗️",
                parse_mode="html",
                reply_markup=keyboard
            )
        else:
            await bot.send_message(user_id, "😔 К сожалению, ключи для выбранного срока закончились. Обратитесь в поддержку при помощи соответствующей кнопки.")
    elif 'reject_payment' in callback_query.data:
        await bot.send_message(user_id, "❌ Админ отклонил ваш платеж. ❌\n\nВозможные причины:\n1. Скриншот не из банковского приложения;\n2. Платеж не поступил на указанные реквизиты;\n3. Другая причина.\n\nЕсли вы уверены, что это ошибка, пожалуйста, обратитесь в поддержку с помощью соответствующего выбора в главном меню.")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'instruction')
async def send_instruction(callback_query: types.CallbackQuery):
    await bot.send_message(
        callback_query.from_user.id,
        "✏️ Инструкция по подключению доступна по ссылке: https://telegra.ph/Nastrojka-klienta-dlya-VPN-Na-PK-iOS-i-Android-08-08",
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start"))
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'back_to_start')
async def back_to_start(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    await send_welcome(callback_query.message)

def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["💰 Купить", "ℹ️ Профиль", "🆘 Поддержка", "😻 Тестовый период", "🗒 Инструкция по подключению"]
    keyboard.add(*buttons)
    return keyboard

# Обработка нажатия кнопки "💳 Банковской картой"
@dp.message_handler(lambda message: message.text == "💳 Банковской картой", state=PaymentState.waiting_for_payment_method)
async def pay_with_card(message: types.Message, state: FSMContext):
    data = await state.get_data()
    duration = data['duration']
    amount = data['amount']

    # Генерация уникального идентификатора для платежа
    payment_label = str(uuid.uuid4())

    # Создание платежа с использованием Yoomoney API
    quickpay = Quickpay(
        receiver=YOOMONEY_WALLET,
        quickpay_form="shop",
        targets="Оплата подписки на VPN",
        paymentType="AC",  # 'AC' для оплаты с карты
        sum=amount,
        label=payment_label  # Используем уникальный идентификатор в качестве метки для идентификации платежа
    )
    payment_url = quickpay.redirected_url

    # Отправка ссылки для оплаты пользователю
    await message.answer(f"Для оплаты перейдите по ссылке: {payment_url}\nПосле оплаты бот автоматически подтвердит ваш платеж.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Назад"))

    # Ожидание и проверка платежа
    if await check_payment(message.from_user.id, duration, amount):
        # Проверка, выдан ли ключ за текущий платеж
        cursor.execute('SELECT key FROM issued_keys WHERE user_id = ? AND duration = ?', (message.from_user.id, duration))
        existing_key = cursor.fetchone()

        if existing_key:
            # Ключ уже выдан за этот платеж
            await message.answer("Ваш платеж подтвержден. Ключ уже был выдан для текущего платежа. Обратитесь в поддержку, если у вас возникли вопросы.")
        else:
            # Платеж прошел, выдаем новый ключ
            cursor.execute('SELECT key FROM vpn_keys WHERE is_used = 0 AND duration = ? LIMIT 1', (duration,))
            key = cursor.fetchone()
            if key:
                cursor.execute('UPDATE vpn_keys SET is_used = 1 WHERE key = ?', (key[0],))
                conn.commit()

                # Добавляем запись в таблицу issued_keys
                cursor.execute('INSERT INTO issued_keys (user_id, payment_label, key, issued) VALUES (?, ?, ?, ?)', (message.from_user.id, payment_label, key[0], True))
                conn.commit()

                # Отправка сообщения с ключом и инструкцией
                keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add("🗒 Инструкция по подключению")
                await message.answer(
                    f"<b>Ваш платеж подтвержден.</b>\nВот ваш ключ на {duration} мес.: <code>{key[0]}</code>\n\n<b>❗️Нажмите на ключ, чтобы скопировать его❗️</b>\n\nИнструкция по подключению доступна по кнопке ниже.",
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
            else:
                await message.answer("К сожалению, ключи закончились. Пожалуйста, свяжитесь с поддержкой.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Назад"))
    else:
        await message.answer("Платеж не был завершен. Попробуйте снова или свяжитесь с поддержкой.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Назад"))

    await state.finish()

# Функция для проверки платежа
async def check_payment(user_id, duration, amount):
    amount = round(amount, 2)  # Округляем ожидаемую сумму до двух знаков после запятой
    tolerance = 0.01  # Пороговое значение для учета возможной комиссии

    for _ in range(60):  # 60 попыток проверки платежа
        history = client.operation_history(label=str(user_id))
        successful_operations = []
        for operation in history.operations:
            if operation.status == "success":
                successful_operations.append(operation)
        
        for operation in successful_operations:
            if abs(round(operation.amount, 2) - amount * 0.97) <= tolerance:  # Учитываем 3% комиссию
                return True
        
        await asyncio.sleep(10)  # Проверка каждые 10 секунд
    return False

# Обработка нажатия кнопки "🗒 Инструкция по подключению"
@dp.callback_query_handler(lambda c: c.data == 'instruction')
async def send_instruction(callback_query: types.CallbackQuery):
    # Отправка инструкции
    await bot.send_message(
        callback_query.from_user.id,
        "✏️ Инструкция по подключению доступна по ссылке: https://telegra.ph/Nastrojka-klienta-dlya-VPN-Na-PK-iOS-i-Android-08-08",
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start"))
    )
    await callback_query.answer()

# Обработка нажатия кнопки "⬅️ Назад"
@dp.callback_query_handler(lambda c: c.data == 'back_to_start')
async def back_to_start(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    await send_welcome(callback_query.message)

# Клавиатура главного меню
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["💰 Купить", "ℹ️ Профиль", "🆘 Поддержка", "😻 Тестовый период", "🗒 Инструкция по подключению"]
    keyboard.add(*buttons)
    return keyboard

# Обработка нажатия кнопки "Профиль"
@dp.message_handler(lambda message: message.text == "ℹ️ Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('SELECT username, first_name, last_name, subscription_end_date FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        username, first_name, last_name, subscription_end_date = user
        if subscription_end_date:
            subscription_end_date = f"до {subscription_end_date}"
            days_left = (datetime.strptime(subscription_end_date, "%Y-%m-%d") - datetime.now()).days
        else:
            subscription_end_date = "Не активна"
            days_left = "Не применимо"
        message_text = (
            f"Имя: {first_name} {last_name}\n"
            f"Юзернейм: @{username}\n"
            f"Статус подписки: {subscription_end_date}\n"
            f"Осталось дней: {days_left}"
        )
    else:
        message_text = "Информация о пользователе не найдена."

    await message.answer(message_text, reply_markup=main_menu())

# Обработка нажатия кнопки "Поддержка"
@dp.message_handler(lambda message: message.text == "🆘 Поддержка")
async def support(message: types.Message):
    support_link = "https://t.me/unbeatzy"  # Замените на актуальный ссылку
    await message.answer(f"Связаться с поддержкой: {support_link}", reply_markup=main_menu())

# Обработка нажатия кнопки "😻 Тестовый период"
@dp.message_handler(lambda message: message.text == "😻 Тестовый период")
async def trial_period(message: types.Message):
    # Клавиатура
    keyboard = InlineKeyboardMarkup()
    button_bot = InlineKeyboardButton(text="🤖 Перейти в бота", url="https://t.me/beatvpn_test_sub_bot")
    button_back = InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")
    keyboard.add(button_bot, button_back)
    
    await message.answer(
        "Для новых пользователей, которые еще не приобретали подписку, действует акция: бесплатный тестовый период на три дня.\nТестовый период выдается только один раз для одного пользователя! Повторно воспользоваться тестовым периодом невозможно!\n\nЧтобы получить бесплатный тестовый ключ, нажмите на кнопку 🤖 Перейти в бота и следуйте его инструкции.\nБот вышлет вам ключ, который будет действовать 3 дня с момента добавления его в приложение.\n\n\n\n<b>Если вы уже воспользовались тестовым периодом - повторно ключ не выдается.</b>",
        reply_markup=keyboard,
        parse_mode="html"
    )

# Обработка нажатия кнопки "⬅️ Назад"
@dp.callback_query_handler(lambda c: c.data == "back_to_start")
async def back_to_start(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    await send_welcome(callback_query.message)

# Обработка нажатия кнопки "🗒 Инструкция по подключению"
@dp.message_handler(lambda message: message.text == "🗒 Инструкция по подключению")
async def buy(message: types.Message):
    # Клавиатура
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["⬅️ Назад"]
    keyboard.add(*buttons)
    await message.answer("✏️ Инструкция по подключению доступна по ссылке: https://telegra.ph/Nastrojka-klienta-dlya-VPN-Na-PK-iOS-i-Android-08-08", reply_markup=keyboard)

# Команда для загрузки ключей (только для администратора)
@dp.message_handler(commands=['add_keys'])
async def add_keys(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        await message.answer("🕘 Отправьте срок действия ключей (в месяцах):")
        await AddKeysState.waiting_for_duration.set()
    else:
        await message.answer("❌ У вас нет прав для выполнения этой команды. ❌")

# Ожидание ввода срока действия ключей от администратора
@dp.message_handler(state=AddKeysState.waiting_for_duration, content_types=types.ContentTypes.TEXT)
async def process_duration(message: types.Message, state: FSMContext):
    duration = int(message.text)
    await state.update_data(duration=duration)
    await AddKeysState.waiting_for_keys.set()
    await message.answer("🔑 Теперь отправьте ключи, каждый с новой строки:")

# Ожидание ключей и сохранение их в базе данных
@dp.message_handler(state=AddKeysState.waiting_for_keys, content_types=types.ContentTypes.TEXT)
async def process_keys(message: types.Message, state: FSMContext):
    keys = message.text.splitlines()
    data = await state.get_data()
    duration = data.get('duration')
    for key in keys:
        cursor.execute('INSERT INTO vpn_keys (key, duration, is_used) VALUES (?, ?, ?)', (key, duration, False))
    conn.commit()
    await state.finish()
    await message.answer("Ключи успешно добавлены! ✅")

# Команда для массовой рассылки сообщения (только для администратора)
@dp.message_handler(commands=['broadcast'])
async def broadcast(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        await message.answer("📝 Отправьте сообщение для рассылки всем пользователям.")
        await BroadcastState.waiting_for_message.set()
    else:
        await message.answer("❌ У вас нет прав для выполнения этой команды. ❌")

# Ожидание от администратора текста для рассылки
@dp.message_handler(state=BroadcastState.waiting_for_message, content_types=types.ContentTypes.TEXT)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    broadcast_message = message.text
    cursor.execute('SELECT id FROM users')
    users = cursor.fetchall()
    for user in users:
        try:
            await bot.send_message(user[0], broadcast_message)
        except Exception as e:
            print(f"❌ Не удалось отправить сообщение пользователю {user[0]}: {e}")
    await state.finish()
    await message.answer("Рассылка завершена. ✅")

# Команда для просмотра активных ключей (только для администратора)
@dp.message_handler(commands=['view_active_keys'])
async def view_active_keys(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        cursor.execute('SELECT key, duration FROM vpn_keys WHERE is_used = 0')
        active_keys = cursor.fetchall()
        
        if active_keys:
            response = "🔑 Список активных ключей:\n\n"
            for key, duration in active_keys:
                response += f"Ключ: {key}\nСрок действия: {duration} мес.\n\n"
        else:
            response = "😔 Нет активных ключей."
        
        await message.answer(response)
    else:
        await message.answer("❌ У вас нет прав для выполнения этой команды. ❌")

# Запуск бота
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
