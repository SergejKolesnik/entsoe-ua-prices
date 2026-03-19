import os
import requests
import csv
from datetime import datetime, timedelta

def get_oree_prices():
    # Визначаємо дату на завтра (РДН)
    target_date = datetime.now() + timedelta(days=1)
    date_str = target_date.strftime('%d.%m.%Y')
    
    # URL для отримання даних (JSON формат)
    url = f"https://www.oree.com.ua/index.php/PXS/get_data_main_page/{date_str}/1"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }

    print(f"Запит цін до 'Оператора ринку' на {date_str}...")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Помилка сайту: {response.status_code}")
            return

        data = response.json()
        # Шукаємо дані РДН (ОЕС України)
        # Зазвичай це структура з цінами по годинах
        if 'BAU' in data and 'table' in data['BAU']:
            rows = data['BAU']['table']
            
            file_name = 'prices_history.csv'
            file_exists = os.path.isfile(file_name)
            
            with open(file_name, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price_UAH_MWh'])
                
                for row in rows:
                    hour = row['Hour']
                    price = row['Price'] # Ціна РДН
                    writer.writerow([target_date.date(), f"{int(hour):02d}:00", price])
            
            print(f"УСПІХ! Дані за {target_date.date()} завантажені з oree.com.ua")
        else:
            print("Дані на сайті oree.com.ua ще не оновлені. Спробуйте пізніше.")

    except Exception as e:
        print(f"Помилка при отриманні даних з Орее: {e}")

if __name__ == "__main__":
    get_oree_prices()
