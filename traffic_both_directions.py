import os
import re
import time
import random
from datetime import datetime, timedelta, timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ============================================
# НАСТРОЙКИ (БЕРУТСЯ ИЗ СЕКРЕТОВ GITHUB)
# ============================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WARNING_THRESHOLD = int(os.environ.get('WARNING_THRESHOLD', 25))
ALWAYS_NOTIFY = os.environ.get('ALWAYS_NOTIFY', 'False').lower() == 'true'

# ============================================
# КООРДИНАТЫ МАРШРУТОВ (ВАШИ ПОСЛЕДНИЕ)
# ============================================
ROUTES = {
    'to_vladimir': {
        'name': 'Лакинск → Владимир',
        'start': '56.028989,40.006655',
        'end': '56.105213,40.296923'
    },
    'to_lakinsk': {
        'name': 'Владимир → Лакинск',
        'start': '56.112379,40.326794',
        'end': '56.028989,40.006655'
    }
}

# ============================================
# ФУНКЦИЯ ПАРСИНГА ВРЕМЕНИ С ЯНДЕКС.КАРТ
# ============================================

def get_traffic_time(start_coords, end_coords, max_retries=3):
    # Случайная задержка 10-25 секунд (чтобы не быть слишком предсказуемым)
    delay = random.randint(10, 25)
    print(f"   ⏱️ Случайная задержка {delay} сек...")
    time.sleep(delay)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    for attempt in range(max_retries):
        driver = None
        try:
            print(f"   Попытка {attempt+1}...")
            driver = webdriver.Chrome(options=options)
            
            # Формируем URL для маршрута на Яндекс.Картах
            url = f"https://yandex.ru/maps/?rtext={start_coords}~{end_coords}&rtp=1"
            print(f"   Загружаю: {url[:70]}...")
            
            driver.get(url)
            
            # Ждём загрузки карты и появления времени
            wait = WebDriverWait(driver, 20)
            
            # Пробуем разные возможные селекторы
            selectors = [
                ".travel-time-view__title",
                ".route-duration",
                ".time-value",
                "[class*='duration']",
                "[class*='time']"
            ]
            
            time_element = None
            for selector in selectors:
                try:
                    time_element = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    print(f"   Найден элемент с селектором: {selector}")
                    break
                except:
                    continue
            
            if not time_element:
                raise Exception("Не найден элемент со временем")
            
            time_text = time_element.text
            print(f"   Текст с временем: {time_text}")
            
            # Извлекаем минуты из текста
            minutes = 0
            hours_match = re.search(r'(\d+)\s*час', time_text)
            minutes_match = re.search(r'(\d+)\s*мин', time_text)
            
            if hours_match:
                minutes += int(hours_match.group(1)) * 60
            if minutes_match:
                minutes += int(minutes_match.group(1))
            
            if minutes == 0:
                numbers = re.findall(r'\d+', time_text)
                if numbers:
                    minutes = int(numbers[0])
            
            if minutes > 0:
                print(f"✅ Получено время: {minutes} мин")
                return minutes
            else:
                raise Exception(f"Не удалось распарсить время из текста: {time_text}")
                
        except Exception as e:
            print(f"   Ошибка в попытке {attempt+1}: {e}")
            time.sleep(3)
        finally:
            if driver:
                driver.quit()
    
    print("❌ Все попытки не удались")
    return None

# ============================================
# ФУНКЦИЯ ОТПРАВКИ В TELEGRAM
# ============================================

def send_telegram(message):
    """Отправляет сообщение в группу Telegram"""
    import requests
    
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram токен или chat_id не настроены")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return True
        else:
            print(f"❌ Ошибка Telegram API: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

# ============================================
# ФУНКЦИЯ ПРОВЕРКИ ОДНОГО МАРШРУТА
# ============================================

def check_route(route_key, route_data):
    """Проверяет один маршрут и возвращает результат"""
    print(f"\n🔄 Проверка: {route_data['name']}")
    
    traffic_time = get_traffic_time(route_data['start'], route_data['end'])
    
    if traffic_time is None:
        print(f"❌ Не удалось получить данные для {route_data['name']}")
        return None
    
    # Формируем сообщение
    moscow_tz = timezone(timedelta(hours=3))
    moscow_time = datetime.now(moscow_tz)
    
    message = f"🚗 <b>{route_data['name']}</b>\n"
    message += f"⏱️ Время в пути (с пробками): <b>{traffic_time} мин</b>\n"
    message += f"🕐 {moscow_time.strftime('%d.%m.%Y %H:%M')}\n"
    message += f"🔍 Источник: Яндекс.Карты\n"
    
    # Проверяем порог
    is_warning = traffic_time > WARNING_THRESHOLD
    if is_warning:
        message += f"\n🔴 <b>ПРОБКА!</b> Превышен порог {WARNING_THRESHOLD} мин!\n"
    
    return {
        'message': message,
        'is_warning': is_warning,
        'time': traffic_time
    }

# ============================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================

def main():
    print(f"\n{'='*50}")
    print(f"🚀 Запуск проверки {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"📊 Режим: ПАРСИНГ Яндекс.Карт (бесплатно, с пробками)")
    print('='*50)
    
    results = []
    any_warning = False
    
    for route_key, route_data in ROUTES.items():
        result = check_route(route_key, route_data)
        if result:
            results.append(result)
            if result['is_warning']:
                any_warning = True
    
    # Отправляем уведомления
    if ALWAYS_NOTIFY or any_warning:
        print("\n📨 Отправка уведомлений...")
        for result in results:
            if ALWAYS_NOTIFY or result['is_warning']:
                sent = send_telegram(result['message'])
                if sent:
                    print(f"✅ Отправлено: {result['time']} мин")
                else:
                    print(f"❌ Ошибка отправки")
    else:
        print(f"\n⏸️ Нет пробок (порог {WARNING_THRESHOLD} мин), уведомления не отправляются")
    
    print(f"\n✅ Проверка завершена")

if __name__ == "__main__":
    main()
