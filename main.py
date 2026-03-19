import os
import requests
import csv
from datetime import datetime, timedelta

def get_market_operator_prices():
    # Нам потрібні ціни на завтра (РДН)
    target_date = datetime.now() + timedelta(days=1)
    date_str = target_date.strftime('%d.%m.%Y')
    
    # Використовуємо офіційну адресу архіву результатів торгів
    url = f"https://www.oree.com.ua/index.php/PXS/get_data_main_page/{date_str}/1"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.oree.com.ua/'
    }

    print(f"Запит до oree.com.ua за {date_str}...")

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            # Якщо на завтра ще немає, беремо за сьогодні
            print("На завтра ще не опубліковано, беремо сьогоднішні дані...")
            target_date = datetime.now()
            date_str = target_date.strftime('%d.%m.%Y')
            url = f"https://www.oree.com.ua/index.php/PXS/get_data_main_page/{date_str}/1"
            response = requests.get(url, headers=headers)

        data = response.json()
        
        # Структура Орее: BAU (ОЕС України), table (годинні ціни)
        if 'BAU' in data and 'table' in data['BAU']:
            prices_table = data['BAU']['table']
            
            file_name = 'prices_history.csv'
            file_exists = os.path.isfile(file_name)
            
            with open(file_name, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price_UAH_MWh'])
                
                for row in prices_table:
                    # 'Hour' та 'Price' — це ключі в їхньому JSON
                    writer.writerow([target_date.date(), f"{int(row['Hour']):02d}:00", row['Price']])
            
            print(f"Успішно! {len(prices_table)} годин за {target_date.date()} додано в CSV.")
        else:
            print("Дані знайдені, але формат таблиці змінився або вона порожня.")
            
    except Exception as e:
        print(f"Помилка: {e}")

if __name__ == "__main__":
    get_market_operator_prices()
