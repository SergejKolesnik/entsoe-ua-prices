import os
import requests
import csv
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

def get_ukraine_prices():
    # Нам потрібні ціни на сьогодні (20.03.2026)
    target_date = datetime.now()
    date_formatted = target_date.strftime('%d.%m.%Y')
    
    # Використовуємо пряме посилання на XML-архів (ОЕС України)
    # Це найбільш стабільний шлях до офіційних цифр
    url = f"https://www.oree.com.ua/index.php/PXS/get_isp_archive_xml/{date_formatted}/1"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0',
        'Accept': 'application/xml'
    }

    print(f"Запит до архіву Орее на {date_formatted}...")

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Сайт відповів помилкою: {response.status_code}")
            return

        # Парсимо XML
        root = ET.fromstring(response.content)
        
        file_name = 'prices_history.csv'
        file_exists = os.path.isfile(file_name)
        
        count = 0
        with open(file_name, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date', 'Hour', 'Price_UAH_MWh'])
            
            # В архіві Орее дані зазвичай у тегах <item>
            for item in root.findall('.//item'):
                hour = item.find('hour').text
                price = item.find('price').text
                writer.writerow([target_date.date(), f"{int(hour):02d}:00", price])
                count += 1
        
        if count > 0:
            print(f"УСПІХ! {count} годин за {target_date.date()} додано до CSV.")
        else:
            print("Файл отримано, але він порожній. Можливо, торги ще не завершені.")

    except Exception as e:
        print(f"Помилка при читанні архіву: {e}")

if __name__ == "__main__":
    get_ukraine_prices()
