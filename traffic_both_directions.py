import requests
import os
from datetime import datetime
import json

# ============================================
# НАСТРОЙКИ БЕРУТСЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ============================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WARNING_THRESHOLD = int(os.environ.get('WARNING_THRESHOLD', 45))  # по умолчанию 45 минут
ALWAYS_NOTIFY = os.environ.get('ALWAYS_NOTIFY', 'False').lower() == 'true'

# ============================================
# КООРДИНАТЫ МАРШРУТОВ
# ============================================
ROUTES = {
    'to_vladimir': {
        'name': 'Лакинск → Владимир',
        'start': {'name': 'Лакинск', 'lat': 56.028989, 'lon': 40.006655},
        'end': {'name': 'Владимир', 'lat': 56.105213, 'lon': 40.296923}
    },
    'to_lakinsk': {
        'name': 'Владимир → Лакинск',
        'start': {'name': 'Владимир', 'lat': 56.105213, 'lon': 40.296923},
        'end': {'name': 'Лакинск', 'lat': 56.028989, 'lon': 40.006655}
    }
}

# ============================================
# ОСНОВНОЙ КОД
# ============================================

def get_route_time(start_coords, end_coords):
    """
    Получает время в пути через OpenStreetMap (бесплатно)
    """
    try:
        # Формат: долгота,широта (для OSRM)
        start = f"{start_coords['lon']},{start_coords['lat']}"
        end = f"{end_coords['lon']},{end_coords['lat']}"
        
        url = f"http://router.project-osrm.org/route/v1/driving/{start};{end}"
        params = {
            'overview': 'false',
            'alternatives': 'false',
            'steps': 'false'
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if response.status_code == 200 and data['code'] == 'Ok':
            duration_seconds = data['routes'][0]['duration']
            duration_minutes = round(duration_seconds / 60)
            distance_meters = data['routes'][0]['distance']
            distance_km = round(distance_meters / 1000, 1)
            
            return {
                'success': True,
                'minutes': duration_minutes,
                'distance': distance_km
            }
        else:
            return {'success': False, 'error': f'OSRM ошибка: {data.get("code", "unknown")}'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def send_telegram(message):
    """Отправляет сообщение в группу Telegram"""
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
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            return True
        else:
            print(f"❌ Ошибка Telegram API: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def check_route(route_key, route_data):
    """Проверяет один маршрут"""
    print(f"\n🔄 Проверка: {route_data['name']}")
    
    result = get_route_time(route_data['start'], route_data['end'])
    
    if not result['success']:
        print(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
        return None
    
    current_time = result['minutes']
    distance = result['distance']
    
    # Формируем сообщение
    message = f"🚗 <b>{route_data['name']}</b>\n"
    message += f"⏱️ Время в пути: <b>{current_time} мин</b>\n"
    message += f"📏 Расстояние: {distance} км\n"
    message += f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    
    # Проверяем порог
    is_warning = current_time > WARNING_THRESHOLD
    if is_warning:
        message += f"\n🔴 <b>ПРОБКА!</b> Превышен порог {WARNING_THRESHOLD} мин!\n"
    
    return {
        'message': message,
        'is_warning': is_warning,
        'time': current_time
    }

def main():
    """Главная функция"""
    print(f"\n{'='*50}")
    print(f"🚀 Запуск проверки {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print('='*50)
    
    results = []
    any_warning = False
    
    # Проверяем каждый маршрут
    for route_key, route_data in ROUTES.items():
        result = check_route(route_key, route_data)
        if result:
            results.append(result)
            if result['is_warning']:
                any_warning = True
    
    # Отправляем сообщения
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
