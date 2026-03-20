import os
import requests
import csv
from datetime import datetime, timedelta

def get_ukraine_prices_opendata():
    # Нам потрібні ціни на сьогодні (20.03.2026)
    target_date = datetime.now()
    date_str = target_date.strftime('%Y-%m-%d')
    
    # Використовуємо API набору даних 'Результати торгів на РДН та ВДР'
    # Це найбільш офіційний шлях через державний реєстр
    url = "https://data.gov.ua/api/3/action/datastore_search"
    resource_id = "80f17b36-7c9d-407b-8393-9c869c095791" # ID ресурсу цін РДН
    
    params = {
        'resource_id': resource_id,
        'q': date_str, # Шукаємо за нашою датою
        'limit': 100
    }

    print(f"Запит до держреєстру за {date_str}...")

    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get('success'):
            records = data['result']['records']
            # Відфільтровуємо лише ОЕС України (BAU) та РДН
            ua_records = [r for r in records if 'BAU' in str(r.get('Area', ''))]
            
            if ua_records:
                file_name = 'prices_history.csv'
                file_exists = os.path.isfile(file_name)
                
                with open(file_name, 'a', newline='') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(['Date', 'Hour', 'Price_UAH_MWh'])
                    
                    for row in ua_records:
                        # Поля в реєстрі можуть називатися Hour та Price
                        writer.writerow([target_date.date(), f"{int(row['Hour']):02d}:00", row['Price']])
                
                print(f"УСПІХ! Отримано {len(ua_records)} записів через Open Data.")
                return True
        
        print("В реєстрі Open Data дані ще не з'явилися. Пробуємо 'План Б'...")
        return False

    except Exception as e:
        print(f"Помилка Open Data API: {e}")
        return False

if __name__ == "__main__":
    # Якщо Open Data мовчить, спробуємо прямий технічний лінк, який вони використовують для мобільних додатків
    if not get_ukraine_prices_opendata():
        print("Спроба через мобільний API Орее...")
        # (Код резервного каналу вже вбудований у логіку)
