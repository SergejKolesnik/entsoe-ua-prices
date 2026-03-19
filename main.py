import os
import requests
import csv
from datetime import datetime, timedelta

def get_ukraine_market_prices():
    # Нам потрібні ціни на завтра
    target_date = datetime.now() + timedelta(days=1)
    
    # Використовуємо API Оператора ринку для завантаження результатів торгів (архів JSON)
    # Це пряме посилання на їхній внутрішній сервіс для відображення графіків
    date_formatted = target_date.strftime('%d.%m.%Y')
    url = f"https://www.oree.com.ua/index.php/PXS/get_data_main_page/{date_formatted}/1"
    
    # Додаємо заголовки, щоб сайт думав, що ми звичайна людина в браузері
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.oree.com.ua/index.php/PXS/Results_v2',
        'X-Requested-With': 'XMLHttpRequest'
    }

    print(f"Запит цін на {date_formatted}...")

    try:
        response = requests.get(url, headers=headers)
        
        # Якщо на завтра ще немає, беремо за сьогодні
        if response.status_code != 200 or not response.json().get('BAU'):
            print("На завтра ще не опубліковано, завантажуємо сьогоднішні ціни...")
            target_date = datetime.now()
            date_formatted = target_date.strftime('%d.%m.%Y')
            url = f"https://www.oree.com.ua/index.php/PXS/get_data_main_page/{date_formatted}/1"
            response = requests.get(url, headers=headers)

        data = response.json()
        
        if 'BAU' in data and 'table' in data['BAU']:
            prices = data['BAU']['table']
            file_name = 'prices_history.csv'
            file_exists = os.path.isfile(file_name)
            
            with open(file_name, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price_UAH_MWh'])
                
                for row in prices:
                    # 'Hour' та 'Price' - стандартні поля в їхній відповіді
                    writer.writerow([target_date.date(), f"{int(row['Hour']):02d}:00", row['Price']])
            
            print(f"Успіх! {len(prices)} годин додано за {target_date.date()}.")
        else:
            print("Помилка: дані отримано, але структура невідома.")

    except Exception as e:
        print(f"Не вдалося отримати дані: {e}")

if __name__ == "__main__":
    get_ukraine_market_prices()
