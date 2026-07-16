import os
import re
import random
import json
from flask import Flask, request, jsonify
from openai import OpenAI

# ==========================================
# 1. НАСТРОЙКА И ЗАГРУЗКА КЛЮЧЕЙ
# ==========================================
app = Flask(__name__)

# Получаем ключ OpenAI из переменных окружения (так безопасно)
# На PythonAnywhere это настраивается в разделе "Environment variables"
# На Railway это настраивается в разделе "Variables"
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("ОШИБКА: Не найден ключ OPENAI_API_KEY в переменных окружения!")
    # Если ключа нет, бот будет работать, но не сможет генерировать истории
    client = None
else:
    client = OpenAI(api_key=api_key)

# Хранилище состояния игры (для простоты в памяти сервера)
# В реальном проекте лучше использовать Redis или базу данных
sessions = {}

# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def roll_dice(text):
    """
    Ищет в тексте команду типа '2d6', '1d20' и возвращает результат броска.
    """
    match = re.search(r'(\d+)d(\d+)', text.lower().replace(" ", ""))
    if match:
        num_dice = int(match.group(1))
        sides = int(match.group(2))
        results = [random.randint(1, sides) for _ in range(num_dice)]
        total = sum(results)
        return total, results
    return None, None

# ==========================================
# 3. ГЛАВНЫЙ ВЕБХУК (ТОЧКА ВХОДА ДЛЯ DIALOGFLOW)
# ==========================================

@app.route('/webhook', methods=['POST'])
def webhook():
    # Получаем JSON от Dialogflow
    req = request.get_json(silent=True, force=True)
    
    # Если пришел пустой запрос - возвращаем ошибку
    if not req:
        return jsonify({"fulfillmentText": "Ошибка: пустой запрос."})

    query_text = req.get('queryResult', {}).get('queryText', '')
    session_id = req.get('session', 'default_user')

    # ================================
    # СЦЕНАРИЙ 1: БРОСОК КУБИКА
    # ================================
    if "кинуть" in query_text.lower() or "бросок" in query_text.lower():
        total, results = roll_dice(query_text)
        if total is not None:
            reply = f"🎲 Вы бросили {query_text}.\nРезультат: {results}.\nСумма: **{total}**."
            return jsonify({"fulfillmentText": reply})
        else:
            return jsonify({"fulfillmentText": "Не понял, какие кубики кидать. Напиши, например: 'Кинуть 2d6' или 'Кинуть 1d20'."})

    # ================================
    # СЦЕНАРИЙ 2: ГЕНЕРАЦИЯ ИСТОРИИ (ДЕЙСТВИЕ ПОЛЬЗОВАТЕЛЯ)
    # ================================
    # Сюда попадают любые осмысленные действия (Осматриваю, Иду, Беру, и т.д.)
    elif len(query_text.split()) > 2 or "хочу" in query_text.lower():
        
        # Бросаем кубик для проверки (по правилам DnD)
        d20_result = random.randint(1, 20)
        
        # Формируем промпт для ChatGPT
        prompt = f"""
        Ты - Мастер игры в D&D (Dungeons & Dragons). 
        Игрок совершает действие: "{query_text}".
        Он кинул кубик d20 и выпало: {d20_result}.
        
        Если число 1-10 - действие проваливается или происходит что-то опасное.
        Если число 11-19 - действие удается с небольшими сложностями.
        Если число 20 - происходит критический успех!
        
        Напиши красочное, эпическое продолжение истории (1-2 абзаца на русском языке), основываясь на результате кубика. 
        В конце задай вопрос: "Что вы будете делать дальше?".
        """

        # Если ключ OpenAI не вставлен, отвечаем заглушкой
        if client is None:
            return jsonify({
                "fulfillmentText": "⚠️ Бот не настроен. Вставьте ключ OpenAI в переменные окружения (OPENAI_API_KEY), чтобы генерировать истории."
            })

        try:
            # Отправляем запрос в ChatGPT с таймаутом (чтобы сервер не завис)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                timeout=25  # Ждем ответа максимум 25 секунд
            )
            
            generated_story = response.choices[0].message.content
            return jsonify({"fulfillmentText": generated_story})

        except Exception as e:
            # Если OpenAI ошибся или тормозит, отвечаем красиво
            return jsonify({
                "fulfillmentText": f"🧙‍♂️ Мастер задумался над вашим действием... (Ошибка: {str(e)})\nДавайте попробуем еще раз через пару секунд!"
            })

    # ================================
    # СЦЕНАРИЙ 3: СТАРТ И ПРОЧИЕ КОМАНДЫ
    # ================================
    elif "start" in query_text.lower() or "новая игра" in query_text.lower():
        return jsonify({
            "fulfillmentText": "🛡️ Добро пожаловать в мир D&D! Вы в таверне. Что будете делать? (Пример: 'Осматриваю зал' или 'Кинуть 1d20')"
        })
        
    else:
        return jsonify({
            "fulfillmentText": "Я вас не понял. Вы можете кинуть кубик (например 'Кинуть 2d6') или описать действие ('Осматриваю комнату')."
        })

# ==========================================
# 4. ЗАПУСК СЕРВЕРА
# ==========================================
if __name__ == '__main__':
    # Для PythonAnywhere порт не важен, для локального теста порт 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
